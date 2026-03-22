from __future__ import annotations

import sys
import unittest
from asyncio import run as asyncio_run
from pathlib import Path
from tempfile import TemporaryDirectory

from starlette.requests import Request


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from luoying_bot.application.services.video_understanding_service import VideoUnderstandingResult
from luoying_bot.infra.web.api import WebApiFactory
from luoying_bot.infra.web.session_store import WebSessionStore


class _FakeVideoUnderstandingService:
    def __init__(self, text: str = "画面里有一只猫在窗边打盹。") -> None:
        self.text = text
        self.calls: list[dict[str, object]] = []

    async def describe_video(self, video_bytes: bytes, file_name: str, content_type: str = "") -> VideoUnderstandingResult:
        self.calls.append(
            {
                "size": len(video_bytes),
                "file_name": file_name,
                "content_type": content_type,
            }
        )
        return VideoUnderstandingResult(
            text=self.text,
            frame_count=3,
            sampled_timestamps=[0.4, 1.2, 2.8],
            model="mock-vision-model",
        )


class WebVideoDescribeApiTest(unittest.TestCase):
    @staticmethod
    def _find_post_endpoint(app, path: str):  # noqa: ANN001
        for route in app.routes:
            if getattr(route, "path", "") == path and "POST" in getattr(route, "methods", set()):
                return route.endpoint
        raise AssertionError(f"endpoint not found: {path}")

    @staticmethod
    def _build_request(app, path: str, body: bytes, headers: list[tuple[bytes, bytes]] | None = None) -> Request:  # noqa: ANN001
        payload = body

        async def receive() -> dict[str, object]:
            nonlocal payload
            if payload is None:
                return {"type": "http.disconnect"}
            chunk = payload
            payload = None
            return {"type": "http.request", "body": chunk, "more_body": False}

        scope = {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": headers or [],
            "query_string": b"",
            "app": app,
        }
        return Request(scope, receive)

    def test_video_describe_returns_assistant_text_final_event(self) -> None:
        app = WebApiFactory().create()
        with TemporaryDirectory() as tmp_dir:
            app.state.web_session_store = WebSessionStore(Path(tmp_dir) / "web_sessions.json")
            fake_service = _FakeVideoUnderstandingService()
            app.state.video_understanding_service = fake_service

            created = app.state.web_session_store.create_session(user_id="u_1", user_name="Alice")
            session_id = created["session_id"]
            endpoint = self._find_post_endpoint(app, "/api/sessions/{session_id}/video/describe")
            request = self._build_request(
                app,
                f"/api/sessions/{session_id}/video/describe",
                body=b"fake-video-bytes",
                headers=[
                    (b"content-type", b"video/mp4"),
                    (b"x-file-name", b"demo.mp4"),
                ],
            )

            response = asyncio_run(
                endpoint(
                    session_id=session_id,
                    request=request,
                    user_id="u_1",
                    user_name="Alice",
                )
            )

            payload = response.model_dump(by_alias=True)
            self.assertEqual(payload["event"]["type"], "assistant.text.final")
            self.assertEqual(payload["event"]["payload"]["text"], "画面里有一只猫在窗边打盹。")
            self.assertEqual(payload["event"]["payload"]["source"], "video_understanding")
            self.assertEqual(payload["event"]["payload"]["frame_count"], 3)
            self.assertEqual(len(fake_service.calls), 1)

            messages = app.state.web_session_store.get_messages(session_id=session_id, user_id="u_1") or []
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[0]["role"], "user")
            self.assertIn("上传视频", messages[0]["text"])
            self.assertEqual(messages[1]["role"], "assistant")

    def test_video_describe_empty_body_returns_structured_400(self) -> None:
        from fastapi import HTTPException

        app = WebApiFactory().create()
        with TemporaryDirectory() as tmp_dir:
            app.state.web_session_store = WebSessionStore(Path(tmp_dir) / "web_sessions.json")
            app.state.video_understanding_service = _FakeVideoUnderstandingService()
            created = app.state.web_session_store.create_session(user_id="u_2", user_name="Bob")
            session_id = created["session_id"]
            endpoint = self._find_post_endpoint(app, "/api/sessions/{session_id}/video/describe")
            request = self._build_request(
                app,
                f"/api/sessions/{session_id}/video/describe",
                body=b"",
                headers=[(b"content-type", b"video/mp4")],
            )

            with self.assertRaises(HTTPException) as ctx:
                asyncio_run(
                    endpoint(
                        session_id=session_id,
                        request=request,
                        user_id="u_2",
                        user_name="Bob",
                    )
                )
            self.assertEqual(ctx.exception.status_code, 400)
            detail = ctx.exception.detail or {}
            self.assertEqual(detail.get("code"), "EMPTY_VIDEO_BODY")
            self.assertEqual(detail.get("status"), 400)

    def test_video_describe_cross_user_session_returns_structured_400(self) -> None:
        from fastapi import HTTPException

        app = WebApiFactory().create()
        with TemporaryDirectory() as tmp_dir:
            app.state.web_session_store = WebSessionStore(Path(tmp_dir) / "web_sessions.json")
            app.state.video_understanding_service = _FakeVideoUnderstandingService()
            created = app.state.web_session_store.create_session(user_id="u_owner", user_name="Owner")
            session_id = created["session_id"]
            endpoint = self._find_post_endpoint(app, "/api/sessions/{session_id}/video/describe")
            request = self._build_request(
                app,
                f"/api/sessions/{session_id}/video/describe",
                body=b"fake-video",
                headers=[(b"content-type", b"video/mp4")],
            )

            with self.assertRaises(HTTPException) as ctx:
                asyncio_run(
                    endpoint(
                        session_id=session_id,
                        request=request,
                        user_id="u_other",
                        user_name="Other",
                    )
                )

            self.assertEqual(ctx.exception.status_code, 400)
            detail = ctx.exception.detail or {}
            self.assertEqual(detail.get("code"), "SESSION_OWNERSHIP_ERROR")
            self.assertEqual(detail.get("status"), 400)
            self.assertIn("session does not belong to current user", str(detail.get("message", "")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
