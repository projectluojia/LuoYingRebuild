from __future__ import annotations

import sys
import unittest
from asyncio import run as asyncio_run
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import HTTPException
from starlette.requests import Request


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from luoying_bot.infra.web.api import ChatRequest, WebApiFactory
from luoying_bot.infra.web.session_store import WebSessionStore


class _RaisingHandler:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    async def handle(self, message):  # noqa: ANN001
        raise self.exc


class WebApiRegressionTest(unittest.TestCase):
    @staticmethod
    def _find_post_endpoint(app, path: str):  # noqa: ANN001
        for route in app.routes:
            if getattr(route, "path", "") == path and "POST" in getattr(route, "methods", set()):
                return route.endpoint
        raise AssertionError(f"endpoint not found: {path}")

    @staticmethod
    def _build_request(app, path: str) -> Request:  # noqa: ANN001
        scope = {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
            "query_string": b"",
            "app": app,
        }
        return Request(scope)

    def test_chat_value_error_returns_structured_400(self) -> None:
        app = WebApiFactory(event_handler=_RaisingHandler(ValueError("bad input"))).create()
        chat_endpoint = self._find_post_endpoint(app, "/chat")
        req = ChatRequest(session_id="s-1", user_id="u-1", user_name="tester", text="hello")
        request = self._build_request(app, "/chat")
        with self.assertRaises(HTTPException) as ctx:
            asyncio_run(chat_endpoint(req=req, request=request))
        detail = ctx.exception.detail
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIsInstance(detail, dict)
        self.assertEqual(detail.get("code"), "BAD_REQUEST")
        self.assertEqual(detail.get("status"), 400)
        self.assertEqual(detail.get("message"), "bad input")

    def test_chat_runtime_error_returns_structured_502(self) -> None:
        app = WebApiFactory(event_handler=_RaisingHandler(RuntimeError("upstream timeout"))).create()
        chat_endpoint = self._find_post_endpoint(app, "/chat")
        req = ChatRequest(session_id="s-2", user_id="u-2", user_name="tester", text="hello")
        request = self._build_request(app, "/chat")
        with self.assertRaises(HTTPException) as ctx:
            asyncio_run(chat_endpoint(req=req, request=request))
        detail = ctx.exception.detail
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIsInstance(detail, dict)
        self.assertEqual(detail.get("code"), "UPSTREAM_RUNTIME_ERROR")
        self.assertEqual(detail.get("status"), 502)
        self.assertEqual(detail.get("message"), "upstream timeout")

    def test_chat_unexpected_error_returns_structured_500(self) -> None:
        app = WebApiFactory(event_handler=_RaisingHandler(Exception("boom"))).create()
        chat_endpoint = self._find_post_endpoint(app, "/chat")
        req = ChatRequest(session_id="s-3", user_id="u-3", user_name="tester", text="hello")
        request = self._build_request(app, "/chat")
        with self.assertRaises(HTTPException) as ctx:
            asyncio_run(chat_endpoint(req=req, request=request))
        detail = ctx.exception.detail
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIsInstance(detail, dict)
        self.assertEqual(detail.get("code"), "INTERNAL_ERROR")
        self.assertEqual(detail.get("status"), 500)
        self.assertIn("Web chat failed: Exception: boom", str(detail.get("message", "")))

    def test_api_chat_cross_user_session_returns_json_http_error(self) -> None:
        app = WebApiFactory().create()
        with TemporaryDirectory() as tmp_dir:
            app.state.web_session_store = WebSessionStore(Path(tmp_dir) / "web_sessions.json")
            store = app.state.web_session_store
            created = store.create_session(
                user_id="u_owner",
                user_name="Owner",
                title="owner session",
            )
            session_id = created["session_id"]

            rich_chat_endpoint = self._find_post_endpoint(app, "/api/chat")
            request = self._build_request(app, "/api/chat")
            req = ChatRequest(
                session_id=session_id,
                user_id="u_other",
                user_name="Other",
                text="should fail",
            )

            with self.assertRaises(HTTPException) as ctx:
                asyncio_run(rich_chat_endpoint(req=req, request=request))
            self.assertEqual(ctx.exception.status_code, 400)
            detail = ctx.exception.detail
            self.assertIsInstance(detail, dict)
            self.assertEqual(detail.get("code"), "SESSION_OWNERSHIP_ERROR")
            self.assertEqual(detail.get("status"), 400)
            self.assertIn("session does not belong to current user", str(detail.get("message", "")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
