from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from luoying_bot.config import settings


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class WebSessionStore:
    path: Path
    _lock: Lock = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        if not self.path.exists():
            self.path.write_text('{"sessions": []}', encoding="utf-8")

    @classmethod
    def from_default_path(cls) -> "WebSessionStore":
        return cls(settings.data_dir / "web_sessions.json")

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            data = {"sessions": []}
        if not isinstance(data, dict):
            return {"sessions": []}
        sessions = data.get("sessions")
        if not isinstance(sessions, list):
            data["sessions"] = []
        return data

    def _write(self, data: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def create_session(self, user_id: str, user_name: str, title: str | None = None) -> dict[str, Any]:
        now = _utc_now_iso()
        session = {
            "session_id": str(uuid.uuid4()),
            "user_id": user_id,
            "user_name": user_name,
            "title": (title or "新会话").strip() or "新会话",
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        with self._lock:
            data = self._read()
            data["sessions"].append(session)
            self._write(data)
        return self._session_summary(session)

    def list_sessions(self, user_id: str) -> list[dict[str, Any]]:
        data = self._read()
        sessions = [
            self._session_summary(session)
            for session in data["sessions"]
            if str(session.get("user_id", "")) == str(user_id)
        ]
        sessions.sort(key=lambda item: item["updated_at"], reverse=True)
        return sessions

    def get_session(self, session_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        data = self._read()
        for session in data["sessions"]:
            if str(session.get("session_id", "")) != str(session_id):
                continue
            if user_id is not None and str(session.get("user_id", "")) != str(user_id):
                return None
            return session
        return None

    def get_messages(self, session_id: str, user_id: str | None = None) -> list[dict[str, Any]] | None:
        session = self.get_session(session_id=session_id, user_id=user_id)
        if session is None:
            return None
        messages = session.get("messages", [])
        return messages if isinstance(messages, list) else []

    def ensure_session(self, session_id: str, user_id: str, user_name: str) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            for session in data["sessions"]:
                if str(session.get("session_id", "")) == str(session_id):
                    if str(session.get("user_id", "")) != str(user_id):
                        raise ValueError("session does not belong to current user")
                    if user_name and str(session.get("user_name", "")) != str(user_name):
                        session["user_name"] = user_name
                        session["updated_at"] = _utc_now_iso()
                        self._write(data)
                    return self._session_summary(session)

            now = _utc_now_iso()
            session = {
                "session_id": session_id,
                "user_id": user_id,
                "user_name": user_name,
                "title": "新会话",
                "created_at": now,
                "updated_at": now,
                "messages": [],
            }
            data["sessions"].append(session)
            self._write(data)
            return self._session_summary(session)

    def append_message(self, session_id: str, user_id: str, role: str, text: str) -> None:
        with self._lock:
            data = self._read()
            for session in data["sessions"]:
                if str(session.get("session_id", "")) != str(session_id):
                    continue
                if str(session.get("user_id", "")) != str(user_id):
                    raise ValueError("session does not belong to current user")
                messages = session.setdefault("messages", [])
                messages.append(
                    {
                        "role": role,
                        "text": text,
                        "timestamp": _utc_now_iso(),
                    }
                )
                if role == "user" and (session.get("title") in {"", "新会话"}):
                    stripped = (text or "").strip()
                    if stripped:
                        session["title"] = stripped[:24]
                session["updated_at"] = _utc_now_iso()
                self._write(data)
                return
            raise ValueError("session not found")

    def _session_summary(self, session: dict[str, Any]) -> dict[str, Any]:
        messages = session.get("messages", [])
        message_count = len(messages) if isinstance(messages, list) else 0
        return {
            "session_id": str(session.get("session_id", "")),
            "user_id": str(session.get("user_id", "")),
            "user_name": str(session.get("user_name", "")),
            "title": str(session.get("title", "新会话") or "新会话"),
            "created_at": str(session.get("created_at", "")),
            "updated_at": str(session.get("updated_at", "")),
            "message_count": message_count,
        }
