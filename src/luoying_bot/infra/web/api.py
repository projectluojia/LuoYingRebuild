from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from luoying_bot.application.event_handler import EventHandler
from luoying_bot.application.services.video_understanding_service import VideoUnderstandingService
from luoying_bot.domain.message import UniMessage
from luoying_bot.domain.result import Reply
from luoying_bot.infra.web.session_store import WebSessionStore

class ChatRequest(BaseModel):
    session_id: str
    user_id: str
    user_name: str = '网页用户'
    text: str

class ChatResponse(BaseModel):
    reply: str


class SessionCreateRequest(BaseModel):
    user_id: str
    user_name: str = '网页用户'
    title: str | None = None


class SessionSummaryResponse(BaseModel):
    session_id: str
    user_id: str
    user_name: str
    title: str
    created_at: str
    updated_at: str
    message_count: int


class SessionCreateResponse(BaseModel):
    session: SessionSummaryResponse


class SessionListResponse(BaseModel):
    sessions: list[SessionSummaryResponse]


class MessageRecordResponse(BaseModel):
    role: str
    text: str
    timestamp: str


class SessionMessagesResponse(BaseModel):
    session: SessionSummaryResponse
    messages: list[MessageRecordResponse]


class RichChatResponse(BaseModel):
    session: SessionSummaryResponse
    reply: str


class AssistantTextFinalPayload(BaseModel):
    from_client: str = Field(alias='from')
    to: str
    text: str
    source: str
    frame_count: int
    model: str
    sampled_timestamps: list[float | None]


class AssistantTextFinalEvent(BaseModel):
    type: str
    session_id: str
    timestamp: str
    payload: AssistantTextFinalPayload


class VideoDescribeResponse(BaseModel):
    session: SessionSummaryResponse
    reply: str
    event: AssistantTextFinalEvent


class ErrorDetail(BaseModel):
    code: str
    message: str
    status: int


class WebApiFactory:
    def __init__(self, event_handler: EventHandler | None = None):
        self.event_handler = event_handler

    @staticmethod
    def _error_detail(status_code: int, code: str, message: str) -> dict[str, str | int]:
        return {
            'code': code,
            'message': message,
            'status': status_code,
        }

    def _raise_http_error(self, status_code: int, code: str, message: str) -> None:
        raise HTTPException(status_code=status_code, detail=self._error_detail(status_code, code, message))

    def create(self) -> FastAPI:
        app = FastAPI(title='Luoying Web Agent')
        app.state.web_session_store = WebSessionStore.from_default_path()
        app.state.video_understanding_service = VideoUnderstandingService()

        # AIGC: 支持从外部在 startup 阶段延迟注入 event_handler
        if self.event_handler is not None:
            app.state.event_handler = self.event_handler

        @app.get('/', response_class=HTMLResponse)
        async def index() -> HTMLResponse:
            html_path = Path(__file__).with_name('index.html')
            return HTMLResponse(html_path.read_text(encoding='utf-8'))

        @app.get('/api/sessions', response_model=SessionListResponse)
        async def list_sessions(request: Request, user_id: str = Query(...)) -> SessionListResponse:
            store = getattr(request.app.state, 'web_session_store')
            sessions = store.list_sessions(user_id=user_id)
            return SessionListResponse(sessions=[SessionSummaryResponse(**item) for item in sessions])

        @app.post('/api/sessions', response_model=SessionCreateResponse)
        async def create_session(req: SessionCreateRequest, request: Request) -> SessionCreateResponse:
            store = getattr(request.app.state, 'web_session_store')
            session = store.create_session(user_id=req.user_id, user_name=req.user_name, title=req.title)
            return SessionCreateResponse(session=SessionSummaryResponse(**session))

        @app.get('/api/sessions/{session_id}/messages', response_model=SessionMessagesResponse)
        async def get_session_messages(session_id: str, request: Request, user_id: str = Query(...)) -> SessionMessagesResponse:
            store = getattr(request.app.state, 'web_session_store')
            session = store.get_session(session_id=session_id, user_id=user_id)
            if session is None:
                self._raise_http_error(404, 'SESSION_NOT_FOUND', 'Session not found')
            messages = store.get_messages(session_id=session_id, user_id=user_id) or []
            return SessionMessagesResponse(
                session=SessionSummaryResponse(**store._session_summary(session)),
                messages=[MessageRecordResponse(**item) for item in messages],
            )

        @app.post('/chat', response_model=ChatResponse)
        async def chat(req: ChatRequest, request: Request) -> ChatResponse:
            reply = await self._handle_web_chat(request=request, req=req, persist_history=False)
            return ChatResponse(reply=reply.text)

        @app.post('/api/chat', response_model=RichChatResponse)
        async def rich_chat(req: ChatRequest, request: Request) -> RichChatResponse:
            store = getattr(request.app.state, 'web_session_store')
            try:
                session = store.ensure_session(
                    session_id=req.session_id,
                    user_id=req.user_id,
                    user_name=req.user_name,
                )
            except ValueError as exc:
                self._raise_http_error(400, 'SESSION_OWNERSHIP_ERROR', str(exc))
            reply = await self._handle_web_chat(request=request, req=req, persist_history=True)
            session = store.get_session(session_id=req.session_id, user_id=req.user_id)
            return RichChatResponse(
                session=SessionSummaryResponse(**store._session_summary(session)),
                reply=reply.text,
            )

        @app.post('/api/sessions/{session_id}/video/describe', response_model=VideoDescribeResponse)
        async def describe_video(
            session_id: str,
            request: Request,
            user_id: str = Query(...),
            user_name: str = Query('网页用户'),
        ) -> VideoDescribeResponse:
            store = getattr(request.app.state, 'web_session_store')
            service = getattr(request.app.state, 'video_understanding_service', None)
            if service is None:
                service = VideoUnderstandingService()
                request.app.state.video_understanding_service = service

            try:
                store.ensure_session(
                    session_id=session_id,
                    user_id=user_id,
                    user_name=user_name,
                )
            except ValueError as exc:
                self._raise_http_error(400, 'SESSION_OWNERSHIP_ERROR', str(exc))

            video_bytes = await request.body()
            if not video_bytes:
                self._raise_http_error(400, 'EMPTY_VIDEO_BODY', '请求体为空，未收到视频')

            raw_file_name = request.headers.get('x-file-name') or 'uploaded_video'
            file_name = unquote(str(raw_file_name))
            content_type = request.headers.get('content-type', '')
            upload_note = f'上传视频：{file_name}'
            try:
                store.append_message(session_id, user_id, 'user', upload_note)
            except ValueError as exc:
                self._raise_http_error(400, 'SESSION_OWNERSHIP_ERROR', str(exc))

            try:
                result = await service.describe_video(
                    video_bytes=video_bytes,
                    file_name=file_name,
                    content_type=content_type,
                )
            except ValueError as exc:
                self._raise_http_error(400, 'BAD_REQUEST', str(exc))
            except RuntimeError as exc:
                self._raise_http_error(502, 'UPSTREAM_RUNTIME_ERROR', str(exc))
            except HTTPException:
                raise
            except Exception as exc:
                self._raise_http_error(500, 'INTERNAL_ERROR', f'Video describe failed: {type(exc).__name__}: {exc}')

            reply_text = (result.text or '').strip() or '视频已处理，但未返回文本结果。'
            try:
                store.append_message(session_id, user_id, 'assistant', reply_text)
            except ValueError as exc:
                self._raise_http_error(400, 'SESSION_OWNERSHIP_ERROR', str(exc))

            session = store.get_session(session_id=session_id, user_id=user_id)
            event = AssistantTextFinalEvent(
                type='assistant.text.final',
                session_id=session_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                payload=AssistantTextFinalPayload(
                    **{
                        'from': 'assistant',
                        'to': user_id,
                        'text': reply_text,
                        'source': 'video_understanding',
                        'frame_count': int(result.frame_count),
                        'model': result.model,
                        'sampled_timestamps': result.sampled_timestamps,
                    }
                ),
            )
            return VideoDescribeResponse(
                session=SessionSummaryResponse(**store._session_summary(session)),
                reply=reply_text,
                event=event,
            )
        return app

    async def _handle_web_chat(self, request: Request, req: ChatRequest, persist_history: bool) -> Reply:
        event_handler = getattr(request.app.state, 'event_handler', None)
        if event_handler is None:
            self._raise_http_error(503, 'HANDLER_NOT_READY', 'Web handler is not ready yet')

        store = getattr(request.app.state, 'web_session_store', None)
        if persist_history and store is not None:
            try:
                store.ensure_session(req.session_id, req.user_id, req.user_name)
                store.append_message(req.session_id, req.user_id, 'user', req.text)
            except ValueError as exc:
                self._raise_http_error(400, 'SESSION_OWNERSHIP_ERROR', str(exc))

        try:
            reply = await event_handler.handle(
                UniMessage.from_web_text(req.session_id, req.user_id, req.user_name, req.text)
            )
        except HTTPException:
            raise
        except ValueError as exc:
            self._raise_http_error(400, 'BAD_REQUEST', str(exc))
        except RuntimeError as exc:
            self._raise_http_error(502, 'UPSTREAM_RUNTIME_ERROR', str(exc))
        except Exception as exc:
            self._raise_http_error(500, 'INTERNAL_ERROR', f'Web chat failed: {type(exc).__name__}: {exc}')

        if persist_history and store is not None and reply.text:
            try:
                store.append_message(req.session_id, req.user_id, 'assistant', reply.text)
            except ValueError as exc:
                self._raise_http_error(400, 'SESSION_OWNERSHIP_ERROR', str(exc))
        return reply
    
#web端相关所有代码由AI后来生成的，我看不懂，前端可以研究研究
