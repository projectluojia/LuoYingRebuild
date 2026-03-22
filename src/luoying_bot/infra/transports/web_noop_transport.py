from __future__ import annotations

from luoying_bot.domain.context import ChatContext
from luoying_bot.domain.message import UniMessage
from luoying_bot.ports.transport import ChatTransport, TransportCapabilityError

# AIGC: Web 模式下的空实现 transport。
# 说明：Web 请求/回复走 HTTP，不需要 QQ 那种双向主动推送。

class WebNoopTransport(ChatTransport):
    async def connect(self) -> None:
        return None

    async def recv_message(self) -> UniMessage:
        raise TransportCapabilityError('WebNoopTransport 不支持 recv_message，请通过 Web API 入口传入消息')

    async def send_text(self, context: ChatContext, text: str) -> None:
        # Web 模式下回复由 HTTP 响应返回，不通过 transport 回推。
        return None

    def resolve_session_scope(self, context: ChatContext) -> str:
        return f"web:session:{context.target.conversation_id}"

    async def startup_self_check(self) -> str:
        return "web transport ready (HTTP response driven)"
