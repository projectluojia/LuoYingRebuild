from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from luoying_bot.application.commands.base import BaseCommand
from luoying_bot.application.commands.dispatcher import CommandDispatcher
from luoying_bot.domain.context import (
    ChannelType,
    ChatContext,
    ConversationTarget,
    Platform,
    UserIdentity,
)
from luoying_bot.domain.result import Reply


def _build_context(user_id: str = "u001") -> ChatContext:
    return ChatContext(
        user=UserIdentity(user_id=user_id, user_name="Tester"),
        target=ConversationTarget(
            channel_type=ChannelType.WEB,
            conversation_id="session-001",
            platform=Platform.WEB,
        ),
    )


class _SimpleCommand(BaseCommand):
    name = "/ok"
    aliases = ["/run"]

    async def validate(self, args: dict[str, str]) -> dict[str, str]:
        return args

    async def execute(self, context: ChatContext, args: dict[str, str]) -> Reply:
        return Reply(text="ok")


class _ArgsCommand(BaseCommand):
    name = "/task"
    aliases = ["/t"]
    args_requried = True
    required_args = {"name": ["n"]}
    optional_args = {"priority": ["p"]}

    async def validate(self, args: dict[str, str]) -> dict[str, str]:
        return args

    async def execute(self, context: ChatContext, args: dict[str, str]) -> Reply:
        return Reply(text=f"name={args['name']}, priority={args.get('priority', 'none')}")


class _OpCommand(BaseCommand):
    name = "/op"
    op_required = True

    async def validate(self, args: dict[str, str]) -> dict[str, str]:
        return args

    async def execute(self, context: ChatContext, args: dict[str, str]) -> Reply:
        return Reply(text="op-ok")


class _DupAliasA(BaseCommand):
    name = "/a"
    aliases = ["/same"]

    async def validate(self, args: dict[str, str]) -> dict[str, str]:
        return args

    async def execute(self, context: ChatContext, args: dict[str, str]) -> Reply:
        return Reply(text="a")


class _DupAliasB(BaseCommand):
    name = "/b"
    aliases = ["/same"]

    async def validate(self, args: dict[str, str]) -> dict[str, str]:
        return args

    async def execute(self, context: ChatContext, args: dict[str, str]) -> Reply:
        return Reply(text="b")


class CommandDispatcherTest(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_command_returns_none(self) -> None:
        dispatcher = CommandDispatcher(services={})
        dispatcher.register(_SimpleCommand({}))
        reply = await dispatcher.dispatch("/missing", _build_context())
        self.assertIsNone(reply)

    def test_register_duplicate_name_raises(self) -> None:
        dispatcher = CommandDispatcher(services={})
        dispatcher.register(_SimpleCommand({}))
        with self.assertRaisesRegex(ValueError, "命令名重复"):
            dispatcher.register(_SimpleCommand({}))

    def test_register_duplicate_alias_raises(self) -> None:
        dispatcher = CommandDispatcher(services={})
        dispatcher.register(_DupAliasA({}))
        with self.assertRaisesRegex(ValueError, "命令别名重复"):
            dispatcher.register(_DupAliasB({}))

    async def test_dispatch_success_with_alias_and_args(self) -> None:
        dispatcher = CommandDispatcher(services={})
        dispatcher.register(_ArgsCommand({}))
        reply = await dispatcher.dispatch("/t n Alice p high", _build_context())
        assert reply is not None
        self.assertEqual(reply.text, "name=Alice, priority=high")

    async def test_dispatch_parse_errors_are_wrapped(self) -> None:
        dispatcher = CommandDispatcher(services={})
        dispatcher.register(_ArgsCommand({}))

        odd = await dispatcher.dispatch("/task name", _build_context())
        missing = await dispatcher.dispatch("/task p high", _build_context())
        unknown = await dispatcher.dispatch("/task x 1 n Alice", _build_context())
        dup = await dispatcher.dispatch("/task n Alice name Bob", _build_context())

        assert odd is not None and missing is not None and unknown is not None and dup is not None
        self.assertIn("出错：参数数量应为偶数", odd.text)
        self.assertIn("出错：缺少必需参数", missing.text)
        self.assertIn("出错：未知参数", unknown.text)
        self.assertIn("出错：参数重复", dup.text)

    async def test_dispatch_op_required_returns_permission_denied(self) -> None:
        dispatcher = CommandDispatcher(services={"ops": ["op001"]})
        dispatcher.register(_OpCommand({"ops": ["op001"]}))
        reply = await dispatcher.dispatch("/op", _build_context(user_id="u001"))
        assert reply is not None
        self.assertEqual(reply.text, "权限不足")


if __name__ == "__main__":
    unittest.main(verbosity=2)
