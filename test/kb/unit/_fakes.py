"""Shared test doubles for the knowledge-base unit tests.

These implement the port interfaces (``luoying_bot.capabilities.knowledge_base.ports``)
and ``ChatModel`` without touching Postgres, the embedding API, or any LLM. Every test
that needs an external collaborator builds one of these instead.
"""

from __future__ import annotations

from typing import Any

from luoying_bot.capabilities.knowledge_base.models import Citation, RetrievedChunk


class FakeChatModel:
    """Minimal stand-in for ``luoying_bot.ports.llm.ChatModel``.

    Returns a scripted response and records every ``chat()`` invocation so tests can
    assert on the prompts that were sent.
    """

    def __init__(self, response: str = "stub answer"):
        self.response = response
        self.calls: list[tuple[list[dict[str, str]], float | None]] = []

    async def chat(self, messages, temperature=None):
        self.calls.append((messages, temperature))
        return self.response


class FakeRagBackend:
    """Stand-in for ``RagBackend``. Returns canned chunks and records search calls."""

    def __init__(self, chunks: list[RetrievedChunk] | None = None):
        self._chunks = list(chunks or [])
        self.calls: list[dict[str, Any]] = []

    async def search(self, *, query, dataset_id, filters, top_k):
        self.calls.append(
            {
                "query": query,
                "dataset_id": dataset_id,
                "filters": dict(filters),
                "top_k": top_k,
            }
        )
        return [RetrievedChunk(text=c.text, score=c.score, citation=c.citation, metadata=dict(c.metadata)) for c in self._chunks]


class FakeAnalyticsBackend:
    """Stand-in for ``AnalyticsBackend``. Returns canned rows and records executed SQL."""

    def __init__(self, rows: list[dict[str, Any]] | None = None):
        self._rows = [dict(row) for row in (rows or [])]
        self.calls: list[dict[str, Any]] = []

    async def execute_select(self, sql, *, limit):
        self.calls.append({"sql": sql, "limit": limit})
        return [dict(row) for row in self._rows]


class FakeEntityBackend:
    """Stand-in for ``EntityBackend``. Serves search items and relation rows."""

    def __init__(
        self,
        items: list[dict[str, Any]] | None = None,
        relations: list[dict[str, Any]] | None = None,
    ):
        self._items = [dict(item) for item in (items or [])]
        self._relations = [dict(rel) for rel in (relations or [])]
        self.search_calls: list[dict[str, Any]] = []
        self.relation_calls: list[dict[str, Any]] = []

    async def search_kb_items(self, *, query, space_id, item_types=None, limit=12):
        self.search_calls.append(
            {
                "query": query,
                "space_id": space_id,
                "item_types": list(item_types or []),
                "limit": limit,
            }
        )
        return [dict(item) for item in self._items]

    async def fetch_entity_relations(self, *, space_id, entity_ids):
        self.relation_calls.append({"space_id": space_id, "entity_ids": list(entity_ids)})
        return [dict(rel) for rel in self._relations]


class FakeStructuredBackend:
    """Stand-in for ``StructuredBackend`` with an in-memory item store."""

    def __init__(self):
        self.items_by_collection: dict[str, list[dict[str, Any]]] = {}
        self.distinct_calls: list[dict[str, Any]] = []
        self._distinct_values: list[str] = []

    async def list_items(self, collection, *, filters, fields=None, limit=20, sort=None):
        return list(self.items_by_collection.get(collection, []))[:limit]

    async def create_item(self, collection, payload):
        bucket = self.items_by_collection.setdefault(collection, [])
        item = {"id": str(len(bucket) + 1), **payload}
        bucket.append(item)
        return item

    async def update_item(self, collection, item_id, payload):
        return {"id": item_id, **payload}

    async def distinct_values(self, collection, field, *, filters=None, limit=10000):
        self.distinct_calls.append({"collection": collection, "field": field, "limit": limit})
        return list(self._distinct_values)

    def set_distinct_values(self, values: list[str]) -> None:
        self._distinct_values = list(values)


def make_chunk(text: str, *, title: str = "doc", source: str = "https://example.test/a", score: float = 1.0) -> RetrievedChunk:
    """Helper to build a RetrievedChunk with a minimal citation."""
    return RetrievedChunk(
        text=text,
        score=score,
        citation=Citation(title=title, source=source),
    )
