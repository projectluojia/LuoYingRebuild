from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from luoying_bot.application.event_handler import EventHandler
from luoying_bot.application.services.group_runtime import GroupRuntime
from luoying_bot.domain.context import (
    ChannelType,
    ChatContext,
    ConversationTarget,
    Platform,
    UserIdentity,
)
from luoying_bot.domain.message import MessageSegment, UniMessage
from luoying_bot.domain.result import Reply


class _FakeTransport:
    def __init__(self) -> None:
        self.sent_text: list[str] = []
        self.pokes: list[tuple[str, str]] = []

    async def send_text(self, context: ChatContext, text: str) -> None:
        self.sent_text.append(text)

    async def group_poke(self, context: ChatContext, user_id: str) -> None:
        self.pokes.append((context.target.conversation_id, user_id))


class _FakeCommands:
    def __init__(self, reply: Reply | None = None) -> None:
        self.reply = reply or Reply(text="cmd-ok")
        self.called_with: list[str] = []

    async def dispatch(self, text: str, context: ChatContext) -> Reply | None:
        self.called_with.append(text)
        return self.reply


class _FakeAgent:
    def __init__(self, answer: str = "agent-ok") -> None:
        self.answer = answer
        self.called = 0

    async def reply(self, message: UniMessage) -> str:
        self.called += 1
        return self.answer


class _FakeQuickReplyService:
    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self.mapping = mapping or {}

    def match(self, text: str) -> str | None:
        return self.mapping.get(text)


def _build_qq_message(text: str, *, at_bot: bool, user_id: str = "u001", group_id: str = "g001") -> UniMessage:
    context = ChatContext(
        user=UserIdentity(user_id=user_id, user_name="Tester"),
        target=ConversationTarget(
            channel_type=ChannelType.GROUP,
            conversation_id=group_id,
            platform=Platform.QQ,
        ),
    )
    message = UniMessage(platform=Platform.QQ, context=context, raw_event={"post_type": "message"})
    if at_bot:
        message.segments.append(MessageSegment(type="at", data={"user_id": "bot001"}))
    message.add_segment("text", text=text)
    return message


class EventHandlerTest(unittest.IsolatedAsyncioTestCase):
    def _build_handler(
        self,
        *,
        runtime: GroupRuntime | None = None,
        commands: _FakeCommands | None = None,
        agent: _FakeAgent | None = None,
        quick_reply_service: _FakeQuickReplyService | None = None,
        transport: _FakeTransport | None = None,
    ) -> tuple[EventHandler, _FakeTransport, _FakeCommands, _FakeAgent]:
        rt = runtime or GroupRuntime(enabled_groups={"g001": True})
        tr = transport or _FakeTransport()
        cmd = commands or _FakeCommands()
        ag = agent or _FakeAgent()
        qrs = quick_reply_service or _FakeQuickReplyService()
        handler = EventHandler(
            transport=tr,
            runtime=rt,
            commands=cmd,
            agent=ag,
            quick_reply_service=qrs,
            trigger_prefix=["/"],
            bot_qq="bot001",
            bot_name="珞樱",
        )
        return handler, tr, cmd, ag

    async def test_banned_user_returns_silent(self) -> None:
        runtime = GroupRuntime(enabled_groups={"g001": True}, banned_users={"u001": True})
        handler, transport, _, agent = self._build_handler(runtime=runtime)
        msg = _build_qq_message("你好", at_bot=True)
        reply = await handler.handle(msg)
        self.assertTrue(reply.silent)
        self.assertEqual(agent.called, 0)
        self.assertEqual(transport.sent_text, [])

    async def test_group_disabled_returns_silent(self) -> None:
        runtime = GroupRuntime(enabled_groups={"g001": False})
        handler, transport, _, agent = self._build_handler(runtime=runtime)
        msg = _build_qq_message("你好", at_bot=True)
        reply = await handler.handle(msg)
        self.assertTrue(reply.silent)
        self.assertEqual(agent.called, 0)
        self.assertEqual(transport.sent_text, [])

    async def test_qq_without_at_returns_silent(self) -> None:
        handler, transport, _, agent = self._build_handler()
        msg = _build_qq_message("你好", at_bot=False)
        reply = await handler.handle(msg)
        self.assertTrue(reply.silent)
        self.assertEqual(agent.called, 0)
        self.assertEqual(transport.sent_text, [])

    async def test_web_message_calls_agent_without_at(self) -> None:
        handler, transport, _, agent = self._build_handler()
        msg = UniMessage.from_web_text("sess-1", "u001", "Tester", "你好")
        reply = await handler.handle(msg)
        self.assertEqual(reply.text, "agent-ok")
        self.assertFalse(reply.silent)
        self.assertEqual(agent.called, 1)
        # Web 端回复走 HTTP，不通过 transport 主动发送
        self.assertEqual(transport.sent_text, [])

    async def test_command_dispatch_and_send_in_qq(self) -> None:
        handler, transport, commands, agent = self._build_handler(commands=_FakeCommands(reply=Reply(text="执行完成")))
        msg = _build_qq_message("/help", at_bot=True)
        reply = await handler.handle(msg)
        self.assertEqual(commands.called_with, ["/help"])
        self.assertEqual(agent.called, 0)
        self.assertEqual(reply.text, "执行完成")
        self.assertEqual(transport.sent_text, ["[CQ:at,qq=u001] 执行完成"])

    async def test_quick_reply_short_circuit(self) -> None:
        qrs = _FakeQuickReplyService(mapping={"你好": "你好呀"})
        handler, transport, _, agent = self._build_handler(quick_reply_service=qrs)
        msg = _build_qq_message("你好", at_bot=False)
        reply = await handler.handle(msg)
        self.assertTrue(reply.silent)
        self.assertEqual(agent.called, 0)
        self.assertEqual(transport.sent_text, ["你好呀"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
