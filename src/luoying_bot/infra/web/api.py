from __future__ import annotations
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from luoying_bot.application.event_handler import EventHandler
from luoying_bot.domain.message import UniMessage

class ChatRequest(BaseModel):
    session_id: str
    user_id: str
    user_name: str = '网页用户'
    text: str

class ChatResponse(BaseModel):
    reply: str

class WebApiFactory:
    def __init__(self, event_handler: EventHandler | None = None):
        self.event_handler = event_handler

    def create(self) -> FastAPI:
        app = FastAPI(title='Luoying Web Agent')

        # AIGC: 支持从外部在 startup 阶段延迟注入 event_handler
        if self.event_handler is not None:
            app.state.event_handler = self.event_handler

        @app.post('/chat', response_model=ChatResponse)
        async def chat(req: ChatRequest, request: Request) -> ChatResponse:
            event_handler = getattr(request.app.state, 'event_handler', None)
            if event_handler is None:
                # AIGC: 初始化未完成时返回显式 503，避免不透明 500
                raise HTTPException(status_code=503, detail='Web handler is not ready yet')

            reply = await event_handler.handle(
                UniMessage.from_web_text(req.session_id, req.user_id, req.user_name, req.text)
            )
            return ChatResponse(reply=reply.text)
        return app
    
#web端相关所有代码由AI后来生成的，我看不懂，前端可以研究研究
