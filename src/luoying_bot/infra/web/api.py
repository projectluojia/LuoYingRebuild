from __future__ import annotations
from fastapi import FastAPI
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
    def __init__(self, event_handler: EventHandler):
        self.event_handler = event_handler
    def create(self) -> FastAPI:
        app = FastAPI(title='Luoying Web Agent')
        @app.post('/chat', response_model=ChatResponse)
        async def chat(req: ChatRequest) -> ChatResponse:
            reply = await self.event_handler.handle(UniMessage.from_web_text(req.session_id, req.user_id, req.user_name, req.text))
            return ChatResponse(reply=reply.text)
        return app
    
#web端相关所有代码由AI后来生成的，我看不懂，前端可以研究研究