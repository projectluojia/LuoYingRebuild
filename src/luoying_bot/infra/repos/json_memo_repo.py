from __future__ import annotations

import json
from pathlib import Path

from luoying_bot.config import settings
from luoying_bot.ports.repos import MemoItem, MemoRepo


class JsonMemoRepo(MemoRepo):
    def __init__(self, memo_dir: Path | None = None):
        self.memo_dir = memo_dir or settings.memo_dir
        self.memo_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: str) -> Path:
        return self.memo_dir / f"memo_{user_id}.json"

    def list_items(self, user_id: str) -> list[MemoItem]:
        path = self._path(user_id)
        if not path.exists():
            return []

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []

        items = data.get("items", [])
        result: list[MemoItem] = []
        for item in items:
            result.append(
                MemoItem(
                    id=str(item.get("id", "")),
                    content=str(item.get("content", "")),
                    tags=list(item.get("tags", []) or []),
                    created_at=str(item.get("created_at", "")),
                    updated_at=str(item.get("updated_at", "")),
                )
            )
        return result

    def save_items(self, user_id: str, items: list[MemoItem]) -> None:
        path = self._path(user_id)
        data = {
            "user_id": str(user_id),
            "items": [
                {
                    "id": item.id,
                    "content": item.content,
                    "tags": item.tags,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                }
                for item in items
            ],
        }
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )