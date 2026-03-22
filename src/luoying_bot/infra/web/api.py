from __future__ import annotations
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from luoying_bot.application.event_handler import EventHandler
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

class WebApiFactory:
    def __init__(self, event_handler: EventHandler | None = None):
        self.event_handler = event_handler

    def create(self) -> FastAPI:
        app = FastAPI(title='Luoying Web Agent')
        app.state.web_session_store = WebSessionStore.from_default_path()

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
                raise HTTPException(status_code=404, detail='Session not found')
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
            session = store.ensure_session(
                session_id=req.session_id,
                user_id=req.user_id,
                user_name=req.user_name,
            )
            reply = await self._handle_web_chat(request=request, req=req, persist_history=True)
            session = store.get_session(session_id=req.session_id, user_id=req.user_id)
            return RichChatResponse(
                session=SessionSummaryResponse(**store._session_summary(session)),
                reply=reply.text,
            )
        return app

    async def _handle_web_chat(self, request: Request, req: ChatRequest, persist_history: bool) -> Reply:
        event_handler = getattr(request.app.state, 'event_handler', None)
        if event_handler is None:
            raise HTTPException(status_code=503, detail='Web handler is not ready yet')

        store = getattr(request.app.state, 'web_session_store', None)
        if persist_history and store is not None:
            store.ensure_session(req.session_id, req.user_id, req.user_name)
            store.append_message(req.session_id, req.user_id, 'user', req.text)

        try:
            reply = await event_handler.handle(
                UniMessage.from_web_text(req.session_id, req.user_id, req.user_name, req.text)
            )
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f'Web chat failed: {type(exc).__name__}: {exc}') from exc

        if persist_history and store is not None and reply.text:
            store.append_message(req.session_id, req.user_id, 'assistant', reply.text)
        return reply
    
#web端相关所有代码由AI后来生成的，我看不懂，前端可以研究研究
