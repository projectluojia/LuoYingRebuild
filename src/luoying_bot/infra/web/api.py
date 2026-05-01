from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from luoying_bot.bootstrap import AppContainer, build_web_container
from luoying_bot.domain.message import UniMessage
from luoying_bot.infra.transports.web_transport import WebTransport

WEB_DIR = Path(__file__).resolve().parent
INDEX_HTML_FILE = WEB_DIR / "index.html"
STATIC_DIR = WEB_DIR / "static"


class ChatRequest(BaseModel):
    session_id: str = Field(default="web-session")
    user_id: str = Field(default="web-user")
    user_name: str = Field(default="网页用户")
    text: str


class ChatResponse(BaseModel):
    reply: str


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_message(req: ChatRequest) -> UniMessage:
    message = UniMessage.from_web_text(
        session_id=req.session_id,
        user_id=req.user_id,
        user_name=req.user_name,
        text=req.text,
    )
    if message.context is not None:
        message.context.request_uid = str(uuid.uuid4())
    return message


class WebApiFactory:
    def create(self) -> FastAPI:
        scheduler_task: asyncio.Task | None = None

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            nonlocal scheduler_task
            container = await build_web_container()
            await container.transport.connect()
            await container.reminder_service.restore_jobs()
            scheduler_task = asyncio.create_task(
                container.scheduler.start(),
                name="luoying-web-scheduler",
            )
            app.state.container = container
            try:
                yield
            finally:
                container.scheduler.stop()
                if scheduler_task is not None:
                    scheduler_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await scheduler_task
                await container.message_processor.aclose(cancel_running=True)
                model = getattr(container.agent, "model", None)
                close = getattr(model, "close", None)
                if close is not None:
                    await close()
                await container.transport.close()

        app = FastAPI(title="Luoying Web Agent", lifespan=lifespan)
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        def container() -> AppContainer:
            current = getattr(app.state, "container", None)
            if current is None:
                raise HTTPException(status_code=503, detail="Web Agent 尚未启动完成")
            return current

        @app.get("/health")
        async def health() -> dict[str, str]:
            return {"ok": "true"}

        @app.get("/", response_class=HTMLResponse)
        async def index() -> str:
            return INDEX_HTML_FILE.read_text(encoding="utf-8")

        @app.post("/chat", response_model=ChatResponse)
        async def chat(req: ChatRequest) -> ChatResponse:
            message = _build_message(req)
            reply = await container().message_processor.process(message)
            return ChatResponse(reply=reply.text)

        @app.post("/chat/stream")
        async def chat_stream(req: ChatRequest) -> StreamingResponse:
            message = _build_message(req)
            ctx = message.context
            if ctx is None or not ctx.request_uid:
                raise HTTPException(status_code=400, detail="消息上下文无效")

            current = container()
            transport = current.transport
            if not isinstance(transport, WebTransport):
                raise HTTPException(status_code=500, detail="Web transport 未正确初始化")

            queue = transport.register_request(ctx.request_uid)
            task = asyncio.create_task(
                current.message_processor.process(message),
                name=f"web-message:{ctx.thread_id}:{ctx.request_uid}",
            )

            async def events():
                try:
                    yield _sse("start", {"request_uid": ctx.request_uid})
                    while True:
                        if task.done() and queue.empty():
                            break

                        try:
                            event = await asyncio.wait_for(queue.get(), timeout=0.1)
                        except asyncio.TimeoutError:
                            continue

                        event_type = str(event.get("type") or "event")
                        payload = {
                            key: value
                            for key, value in event.items()
                            if key not in {"type", "context"}
                        }
                        yield _sse(event_type, payload)

                    reply = await task
                    yield _sse("final", {"reply": reply.text})
                except asyncio.CancelledError:
                    task.cancel()
                    raise
                except Exception as exc:
                    task.cancel()
                    yield _sse("error", {"error": f"{type(exc).__name__}: {exc}"})
                finally:
                    transport.unregister_request(ctx.request_uid)
                    with contextlib.suppress(BaseException):
                        if not task.done():
                            task.cancel()
                        await task
                    yield _sse("done", {})

            return StreamingResponse(events(), media_type="text/event-stream")

        return app

