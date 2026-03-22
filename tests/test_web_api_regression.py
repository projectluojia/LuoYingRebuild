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


class WebApiRegressionTest(unittest.TestCase):
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

            rich_chat_endpoint = None
            for route in app.routes:
                if getattr(route, "path", "") == "/api/chat" and "POST" in getattr(route, "methods", set()):
                    rich_chat_endpoint = route.endpoint
                    break
            self.assertIsNotNone(rich_chat_endpoint)

            scope = {
                "type": "http",
                "method": "POST",
                "path": "/api/chat",
                "headers": [],
                "query_string": b"",
                "app": app,
            }
            request = Request(scope)
            req = ChatRequest(
                session_id=session_id,
                user_id="u_other",
                user_name="Other",
                text="should fail",
            )

            with self.assertRaises(HTTPException) as ctx:
                asyncio_run(rich_chat_endpoint(req=req, request=request))
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("session does not belong to current user", str(ctx.exception.detail))


if __name__ == "__main__":
    unittest.main(verbosity=2)
