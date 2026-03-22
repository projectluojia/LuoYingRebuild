from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from luoying_bot.application.services.quick_reply_service import QuickReplyService
from luoying_bot.application.services.script_workspace_service import ScriptWorkspaceService
from luoying_bot.domain.message import UniMessage
from luoying_bot.infra.web.session_store import WebSessionStore


class UniMessageSmokeTest(unittest.TestCase):
    def test_from_web_text_builds_context(self) -> None:
        msg = UniMessage.from_web_text("sess-1", "u-1", "Alice", "你好")
        self.assertEqual(msg.get_plain_text(), "你好")
        self.assertEqual(msg.context.thread_id, "Platform.WEB:ChannelType.WEB:sess-1")

    def test_to_llm_text_renders_image_segment(self) -> None:
        msg = UniMessage.from_web_text("sess-1", "u-1", "Alice", "")
        msg.add_segment("image", file="demo.png")
        self.assertIn("[图片:demo.png]", msg.to_llm_text())


class QuickReplySmokeTest(unittest.TestCase):
    def test_match_returns_expected_reply(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "quick_replies.json"
            path.write_text(
                json.dumps([{"trigger": "你好", "reply": "你好呀"}], ensure_ascii=False),
                encoding="utf-8",
            )
            service = QuickReplyService(path=path)
            self.assertEqual(service.match("你好"), "你好呀")
            self.assertIsNone(service.match("别的内容"))


class ScriptWorkspaceSmokeTest(unittest.TestCase):
    def test_write_and_read_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ScriptWorkspaceService(root_dir=Path(tmpdir))
            write_result = service.write_script("10001", "hello.py", "print('hi')", overwrite=False)
            read_result = service.read_script("10001", "hello.py")
            self.assertTrue(write_result.ok)
            self.assertTrue(read_result.ok)
            self.assertIn("print('hi')", read_result.text)

    def test_rejects_parent_directory_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ScriptWorkspaceService(root_dir=Path(tmpdir))
            with self.assertRaises(ValueError):
                service.write_script("10001", "../escape.py", "x=1", overwrite=False)


class WebSessionStoreSmokeTest(unittest.TestCase):
    def test_create_list_and_append_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = WebSessionStore(Path(tmpdir) / "web_sessions.json")
            session = store.create_session("u-1", "Alice")
            store.append_message(session["session_id"], "u-1", "user", "你好")
            store.append_message(session["session_id"], "u-1", "assistant", "你好呀")

            sessions = store.list_sessions("u-1")
            messages = store.get_messages(session["session_id"], user_id="u-1")

            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0]["message_count"], 2)
            self.assertEqual(messages[0]["text"], "你好")
            self.assertEqual(messages[1]["role"], "assistant")


if __name__ == "__main__":
    unittest.main(verbosity=2)
