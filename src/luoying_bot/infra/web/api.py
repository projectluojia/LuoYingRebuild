from __future__ import annotations

import asyncio
import contextlib
import io
import json
import mimetypes
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from luoying_bot.bootstrap import AppContainer, build_web_container
from luoying_bot.config import settings
from luoying_bot.domain.context import UserIdentity
from luoying_bot.domain.message import UniMessage
from luoying_bot.infra.web.knowledge_base_api import create_knowledge_base_router
from luoying_bot.infra.transports.web_transport import WebTransport
from luoying_bot.ports.memory import ConversationThread

WEB_DIR = Path(__file__).resolve().parent
INDEX_HTML_FILE = WEB_DIR / "index.html"
STATIC_DIR = WEB_DIR / "static"
MAX_IMAGE_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_FILE_UPLOAD_BYTES = 25 * 1024 * 1024
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
    file_ids: list[str] = Field(default_factory=list, max_length=8)
    text: str


class ChatResponse(BaseModel):
    reply: str


class ConversationThreadResponse(BaseModel):
    thread_id: str
    title: str
    summary: str
    summarized_message_count: int
    archived: bool
    created_at: str | None = None
    updated_at: str | None = None
    user_id: str | None = None
    user_name: str | None = None
    platform: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None


class ConversationListResponse(BaseModel):
    conversations: list[ConversationThreadResponse]


class ConversationMessagesResponse(BaseModel):
    thread_id: str
    messages: list[dict[str, str]]


class ConversationDeleteResponse(BaseModel):
    deleted: bool


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


class FileUploadResponse(BaseModel):
    file_id: str
    file_name: str
    content_type: str
    size: int
    url: str


class WorkspaceTreeResponse(BaseModel):
    user_id: str
    root: dict[str, Any]


async def get_current_web_user() -> WebCurrentUser:
    return WebCurrentUser(
        user_id="web-user",
        user_name="网页用户",
        email=None,
        authenticated=False,
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _safe_upload_path(upload_path: str) -> Path:
    path = _safe_workspace_path(upload_path)
    parts = path.parts
    if len(parts) < 2 or parts[0] != "upload":
        raise HTTPException(status_code=400, detail="上传文件引用无效")
    return path


def _resolve_uploaded_file(file_id: str, user: WebCurrentUser) -> Path:
    safe_path = _safe_upload_path(file_id)
    base = (settings.script_workspace_dir / user.user_id).resolve()
    target = (base / safe_path).resolve()
    if base not in target.parents or not target.exists() or not target.is_file():
        raise HTTPException(status_code=400, detail="文件不存在或已失效")
    return target


def _safe_image_path(image_id: str) -> Path:
    path = _safe_upload_path(image_id)
    if path.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="图片引用无效")
    return path


def _resolve_uploaded_image(image_id: str, user: WebCurrentUser) -> Path:
    target = _resolve_uploaded_file(image_id, user)
    if Path(image_id).suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="图片引用无效")
    return target


def _is_image_workspace_path(file_id: str) -> bool:
    return Path(file_id).suffix.lower() in ALLOWED_IMAGE_EXTENSIONS


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


def _workspace_download_url(user_id: str, file_path: str) -> str:
    return f"/download/{quote(user_id, safe='')}/{quote(file_path, safe='/')}"


def _datetime_text(value: Any) -> str | None:
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return str(value) if value else None


def _thread_response(thread: ConversationThread) -> ConversationThreadResponse:
    context = thread.context
    user = context.user if context is not None else None
    target = context.target if context is not None else None
    return ConversationThreadResponse(
        thread_id=thread.thread_id,
        title=thread.title,
        summary=thread.summary,
        summarized_message_count=thread.summarized_message_count,
        archived=thread.archived,
        created_at=_datetime_text(thread.created_at),
        updated_at=_datetime_text(thread.updated_at),
        user_id=user.user_id if user is not None else None,
        user_name=user.user_name if user is not None else None,
        platform=target.platform.value if target is not None else None,
        channel_type=target.channel_type.value if target is not None else None,
        conversation_id=target.conversation_id if target is not None else None,
    )


def _ensure_thread_access(thread: ConversationThread, user: WebCurrentUser) -> None:
    if thread.context is None:
        return
    if thread.context.user.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="无权访问该对话")


def _with_workspace_download_urls(node: dict[str, Any], user_id: str) -> dict[str, Any]:
    hydrated = dict(node)
    if hydrated.get("type") == "file" and hydrated.get("path"):
        hydrated["url"] = _workspace_download_url(user_id, str(hydrated["path"]))
    else:
        hydrated["children"] = [
            _with_workspace_download_urls(child, user_id)
            for child in hydrated.get("children", [])
            if isinstance(child, dict)
        ]
    return hydrated


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


def _uploaded_file_extension(file: UploadFile) -> str:
    suffix = Path(file.filename or "").suffix.lower()
    if not suffix:
        guessed = mimetypes.guess_extension((file.content_type or "").lower())
        suffix = guessed.lower() if guessed else ""
    if len(suffix) > 16 or any(ch in suffix for ch in ("/", "\\")):
        return ""
    return suffix


def _safe_original_file_name(file_name: str, extension: str) -> str:
    original = Path(file_name or "").name
    stem = Path(original).stem if original else "upload"
    suffix = Path(original).suffix.lower() or extension
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    if not stem:
        stem = "upload"
    if len(stem) > 80:
        stem = stem[:80]
    if len(suffix) > 16 or any(ch in suffix for ch in ("/", "\\")):
        suffix = extension
    return f"{stem}{suffix}"


def _save_workspace_upload(
    *,
    user: WebCurrentUser,
    content: bytes,
    extension: str,
    original_name: str,
) -> tuple[str, Path]:
    upload_dir = settings.script_workspace_dir / user.user_id / "upload"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_original_file_name(original_name, extension)
    target = upload_dir / safe_name
    if target.exists():
        stem = target.stem
        suffix = target.suffix
        for index in range(1, 1000):
            candidate = upload_dir / f"{stem}_{index}{suffix}"
            if not candidate.exists():
                target = candidate
                break
        else:
            target = upload_dir / f"{uuid.uuid4().hex}{extension}"
    target.write_bytes(content)
    return (Path("upload") / target.name).as_posix(), target


def _build_message(req: ChatRequest, user: WebCurrentUser) -> UniMessage:
    message = UniMessage.from_web_text(
        session_id=req.session_id,
        user_id=user.user_id,
        user_name=user.user_name,
        text=req.text,
    )
    for image_id in req.image_ids:
        target = _resolve_uploaded_image(image_id, user)
        message.add_segment("image", file=str(target))
    for file_id in req.file_ids:
        target = _resolve_uploaded_file(file_id, user)
        if _is_image_workspace_path(file_id):
            message.add_segment("image", file=str(target))
        message.add_segment(
            "file",
            file=file_id,
            name=Path(file_id).name,
            size=target.stat().st_size,
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

        app.include_router(
            create_knowledge_base_router(
                container_provider=container,
                current_user_dependency=get_current_web_user,
            )
        )

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

        @app.get("/uploads/images/{image_id:path}")
        async def get_uploaded_image(
            image_id: str,
            user: WebCurrentUser = Depends(get_current_web_user),
        ) -> FileResponse:
            target = _resolve_uploaded_image(image_id, user)
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

        @app.get("/workspace/tree", response_model=WorkspaceTreeResponse)
        async def workspace_tree(
            user: WebCurrentUser = Depends(get_current_web_user),
        ) -> WorkspaceTreeResponse:
            result = container().script_workspace_service.tree_snapshot(user.user_id)
            tree = result.data.get("tree")
            if not result.ok or not isinstance(tree, dict):
                raise HTTPException(status_code=500, detail=result.text or "读取工作区文件树失败")
            return WorkspaceTreeResponse(
                user_id=user.user_id,
                root=_with_workspace_download_urls(tree, user.user_id),
            )

        @app.post("/uploads/images", response_model=ImageUploadResponse)
        async def upload_image(
            file: UploadFile = File(...),
            user: WebCurrentUser = Depends(get_current_web_user),
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

            image_id, _ = _save_workspace_upload(
                user=user,
                content=content,
                extension=extension,
                original_name=file.filename or "",
            )

            return ImageUploadResponse(
                image_id=image_id,
                file_name=Path(file.filename or image_id).name,
                content_type=content_type,
                size=len(content),
                url=f"/uploads/images/{image_id}",
            )

        @app.post("/uploads/files", response_model=FileUploadResponse)
        async def upload_file(
            file: UploadFile = File(...),
            user: WebCurrentUser = Depends(get_current_web_user),
        ) -> FileUploadResponse:
            content = await file.read(MAX_FILE_UPLOAD_BYTES + 1)
            if len(content) > MAX_FILE_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="文件不能超过 25MB")

            file_id, _ = _save_workspace_upload(
                user=user,
                content=content,
                extension=_uploaded_file_extension(file),
                original_name=file.filename or "",
            )
            content_type = file.content_type or "application/octet-stream"
            return FileUploadResponse(
                file_id=file_id,
                file_name=Path(file.filename or file_id).name,
                content_type=content_type,
                size=len(content),
                url=f"/download/{user.user_id}/{file_id}",
            )

        @app.post("/chat", response_model=ChatResponse)
        async def chat(
            req: ChatRequest,
            user: WebCurrentUser = Depends(get_current_web_user),
        ) -> ChatResponse:
            message = _build_message(req, user)
            reply = await container().message_processor.process(message)
            return ChatResponse(reply=reply.text)

        @app.get("/conversations", response_model=ConversationListResponse)
        async def list_conversations(
            limit: int = 50,
            offset: int = 0,
            include_archived: bool = False,
            user: WebCurrentUser = Depends(get_current_web_user),
        ) -> ConversationListResponse:
            current = container()
            threads = current.services.memory.list_threads(
                user=UserIdentity(user_id=user.user_id, user_name=user.user_name),
                limit=limit,
                offset=offset,
                include_archived=include_archived,
            )
            return ConversationListResponse(
                conversations=[_thread_response(thread) for thread in threads]
            )

        @app.get("/conversations/{thread_id}/messages", response_model=ConversationMessagesResponse)
        async def get_conversation_messages(
            thread_id: str,
            limit: int = 1000,
            user: WebCurrentUser = Depends(get_current_web_user),
        ) -> ConversationMessagesResponse:
            current = container()
            thread = current.services.memory.get_thread(thread_id)
            if thread is None:
                raise HTTPException(status_code=404, detail="对话不存在")
            _ensure_thread_access(thread, user)
            return ConversationMessagesResponse(
                thread_id=thread_id,
                messages=current.services.memory.read(thread_id, limit=limit),
            )

        @app.patch("/conversations/{thread_id}/archive", response_model=ConversationThreadResponse)
        async def archive_conversation(
            thread_id: str,
            user: WebCurrentUser = Depends(get_current_web_user),
        ) -> ConversationThreadResponse:
            current = container()
            thread = current.services.memory.get_thread(thread_id)
            if thread is None:
                raise HTTPException(status_code=404, detail="对话不存在")
            _ensure_thread_access(thread, user)
            archived = current.services.memory.archive_thread(thread_id, archived=True)
            if archived is None:
                raise HTTPException(status_code=404, detail="对话不存在")
            return _thread_response(archived)

        @app.patch("/conversations/{thread_id}/restore", response_model=ConversationThreadResponse)
        async def restore_conversation(
            thread_id: str,
            user: WebCurrentUser = Depends(get_current_web_user),
        ) -> ConversationThreadResponse:
            current = container()
            thread = current.services.memory.get_thread(thread_id)
            if thread is None:
                raise HTTPException(status_code=404, detail="对话不存在")
            _ensure_thread_access(thread, user)
            restored = current.services.memory.archive_thread(thread_id, archived=False)
            if restored is None:
                raise HTTPException(status_code=404, detail="对话不存在")
            return _thread_response(restored)

        @app.delete("/conversations/{thread_id}", response_model=ConversationDeleteResponse)
        async def delete_conversation(
            thread_id: str,
            user: WebCurrentUser = Depends(get_current_web_user),
        ) -> ConversationDeleteResponse:
            current = container()
            thread = current.services.memory.get_thread(thread_id)
            if thread is None:
                return ConversationDeleteResponse(deleted=False)
            _ensure_thread_access(thread, user)
            return ConversationDeleteResponse(
                deleted=current.services.memory.delete_thread(thread_id)
            )

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
