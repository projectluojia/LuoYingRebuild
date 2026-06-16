from __future__ import annotations

import json
from pathlib import Path

from luoying_bot.config import settings
from luoying_bot.ports.repos import KnowledgeItem, KnowledgeRepo


class JsonKnowledgeRepo(KnowledgeRepo):
    def __init__(self, db_file: Path | None = None):
        self.db_file = db_file or settings.knowledge_db_file
        self.db_file.parent.mkdir(parents=True, exist_ok=True)

    def list_items(self) -> list[KnowledgeItem]:
        if not self.db_file.exists():
            return []

        try:
            data = json.loads(self.db_file.read_text(encoding="utf-8"))
        except Exception:
            return []

        items = data.get("items", [])
        result: list[KnowledgeItem] = []
        for item in items:
            result.append(
                KnowledgeItem(
                    id=str(item.get("id", "")),
                    title=str(item.get("title", "")),
                    content=str(item.get("content", "")),
                    tags=list(item.get("tags", []) or []),
                    source=str(item.get("source", "")),
                    created_at=str(item.get("created_at", "")),
                    updated_at=str(item.get("updated_at", "")),
                )
            )
        return result

    def save_items(self, items: list[KnowledgeItem]) -> None:
        data = {
            "items": [
                {
                    "id": item.id,
                    "title": item.title,
                    "content": item.content,
                    "tags": item.tags,
                    "source": item.source,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                }
                for item in items
            ],
        }
        self.db_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
