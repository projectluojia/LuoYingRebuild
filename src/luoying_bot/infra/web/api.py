from __future__ import annotations

import asyncio
import contextlib
import io
import json
import mimetypes
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from luoying_bot.bootstrap import AppContainer, build_web_container
from luoying_bot.config import settings
from luoying_bot.domain.message import UniMessage
from luoying_bot.infra.transports.web_transport import WebTransport

WEB_DIR = Path(__file__).resolve().parent
INDEX_HTML_FILE = WEB_DIR / "index.html"
STATIC_DIR = WEB_DIR / "static"
UPLOAD_DIR = settings.web_upload_dir
IMAGE_UPLOAD_DIR = UPLOAD_DIR / "images"
MAX_IMAGE_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
IMAGE_CONTENT_TYPE_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
}


class ChatRequest(BaseModel):
    session_id: str = Field(default="web-session")
    image_ids: list[str] = Field(default_factory=list, max_length=8)
    text: str


class ChatResponse(BaseModel):
    reply: str


class WebCurrentUser(BaseModel):
    user_id: str
    user_name: str
    email: str | None = None
    authenticated: bool = False


class ImageUploadResponse(BaseModel):
    image_id: str
    file_name: str
    content_type: str
    size: int
    url: str


async def get_current_web_user() -> WebCurrentUser:
    return WebCurrentUser(
        user_id="web-user",
        user_name="网页用户",
        email=None,
        authenticated=False,
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _safe_image_id(image_id: str) -> str:
    name = Path(str(image_id or "").strip()).name
    if not name or name != image_id:
        raise HTTPException(status_code=400, detail="图片引用无效")
    if Path(name).suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="图片类型不支持")
    return name


def _resolve_uploaded_image(image_id: str) -> Path:
    safe_id = _safe_image_id(image_id)
    base = IMAGE_UPLOAD_DIR.resolve()
    target = (base / safe_id).resolve()
    if base != target.parent or not target.exists() or not target.is_file():
        raise HTTPException(status_code=400, detail="图片不存在或已失效")
    return target


def _safe_download_user_id(user_id: str) -> str:
    value = str(user_id or "").strip()
    if not value or Path(value).name != value or value in {".", ".."}:
        raise HTTPException(status_code=400, detail="用户标识无效")
    return value


def _safe_workspace_path(file_path: str) -> Path:
    raw = str(file_path or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/"):
        raise HTTPException(status_code=400, detail="文件路径无效")
    parts = [part for part in raw.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise HTTPException(status_code=400, detail="文件路径无效")
    return Path(*parts)


def _resolve_script_download(user_id: str, file_path: str, user: WebCurrentUser) -> Path:
    safe_user_id = _safe_download_user_id(user_id)
    if safe_user_id != user.user_id:
        raise HTTPException(status_code=403, detail="无权下载该用户文件")

    base = (settings.script_workspace_dir / safe_user_id).resolve()
    target = (base / _safe_workspace_path(file_path)).resolve()
    if base != target and base not in target.parents:
        raise HTTPException(status_code=400, detail="文件路径越界")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return target


def _upload_extension(file: UploadFile) -> str:
    original_suffix = Path(file.filename or "").suffix.lower()
    if original_suffix in ALLOWED_IMAGE_EXTENSIONS:
        return original_suffix

    content_type = (file.content_type or "").lower()
    if content_type in IMAGE_CONTENT_TYPE_EXTENSIONS:
        return IMAGE_CONTENT_TYPE_EXTENSIONS[content_type]

    guessed = mimetypes.guess_extension(content_type) if content_type else None
    if guessed and guessed.lower() in ALLOWED_IMAGE_EXTENSIONS:
        return guessed.lower()

    raise HTTPException(status_code=400, detail="图片类型不支持")


def _build_message(req: ChatRequest, user: WebCurrentUser) -> UniMessage:
    message = UniMessage.from_web_text(
        session_id=req.session_id,
        user_id=user.user_id,
        user_name=user.user_name,
        text=req.text,
    )
    for image_id in req.image_ids:
        _resolve_uploaded_image(image_id)
        message.add_segment("image", file=image_id)
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
        IMAGE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
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

        @app.get("/auth/me", response_model=WebCurrentUser)
        async def auth_me(
            user: WebCurrentUser = Depends(get_current_web_user),
        ) -> WebCurrentUser:
            return user

        @app.post("/auth/logout")
        async def auth_logout() -> dict[str, bool]:
            return {"ok": True}

        @app.get("/uploads/images/{image_id}")
        async def get_uploaded_image(image_id: str) -> FileResponse:
            target = _resolve_uploaded_image(image_id)
            return FileResponse(target)

        @app.get("/download/{user_id}/{file_path:path}")
        async def download_script_file(
            user_id: str,
            file_path: str,
            user: WebCurrentUser = Depends(get_current_web_user),
        ) -> FileResponse:
            target = _resolve_script_download(user_id, file_path, user)
            media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            return FileResponse(target, media_type=media_type, filename=target.name)

        @app.post("/uploads/images", response_model=ImageUploadResponse)
        async def upload_image(
            file: UploadFile = File(...),
            _: WebCurrentUser = Depends(get_current_web_user),
        ) -> ImageUploadResponse:
            content_type = (file.content_type or "").lower()
            if not content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail="仅支持图片上传")

            extension = _upload_extension(file)
            content = await file.read(MAX_IMAGE_UPLOAD_BYTES + 1)
            if len(content) > MAX_IMAGE_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="图片不能超过 10MB")
            try:
                with Image.open(io.BytesIO(content)) as image:
                    image.verify()
            except (UnidentifiedImageError, OSError):
                raise HTTPException(status_code=400, detail="图片内容无效")

            image_id = f"{uuid.uuid4().hex}{extension}"
            target = IMAGE_UPLOAD_DIR / image_id
            target.write_bytes(content)

            return ImageUploadResponse(
                image_id=image_id,
                file_name=Path(file.filename or image_id).name,
                content_type=content_type,
                size=len(content),
                url=f"/uploads/images/{image_id}",
            )

        @app.post("/chat", response_model=ChatResponse)
        async def chat(
            req: ChatRequest,
            user: WebCurrentUser = Depends(get_current_web_user),
        ) -> ChatResponse:
            message = _build_message(req, user)
            reply = await container().message_processor.process(message)
            return ChatResponse(reply=reply.text)

        @app.post("/chat/stream")
        async def chat_stream(
            req: ChatRequest,
            user: WebCurrentUser = Depends(get_current_web_user),
        ) -> StreamingResponse:
            message = _build_message(req, user)
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

