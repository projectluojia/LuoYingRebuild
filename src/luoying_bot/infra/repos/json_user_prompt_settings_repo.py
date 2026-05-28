from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from luoying_bot.ports.repos import UserPromptSettings, UserPromptSettingsRepo


class JsonUserPromptSettingsRepo(UserPromptSettingsRepo):
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def get(self, user_id: str) -> UserPromptSettings | None:
        row = self._read().get(user_id)
        if not isinstance(row, dict):
            return None
        extra_trait_levels = row.get("extra_trait_levels", {})
        if not isinstance(extra_trait_levels, dict):
            extra_trait_levels = {}
        return UserPromptSettings(
            user_id=user_id,
            basic_style=str(row.get("basic_style") or "默认"),
            extra_trait_levels={str(k): str(v) for k, v in extra_trait_levels.items()},
        )

    def save(self, settings: UserPromptSettings) -> None:
        with self._lock:
            data = self._read()
            data[settings.user_id] = {
                "basic_style": settings.basic_style,
                "extra_trait_levels": settings.extra_trait_levels,
            }
            self._write(data)

    def delete(self, user_id: str) -> bool:
        with self._lock:
            data = self._read()
            existed = user_id in data
            if existed:
                del data[user_id]
                self._write(data)
            return existed
