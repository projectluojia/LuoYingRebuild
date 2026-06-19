from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from luoying_bot.capabilities.knowledge_base.analytics import KnowledgeAnalyticsEngine
from luoying_bot.capabilities.knowledge_base.models import Citation, KnowledgeQuery, RetrievalResult, StructuredRecord
from luoying_bot.capabilities.knowledge_base.ports import RagBackend, StructuredBackend


@dataclass(slots=True)
class KBQueryAgentConfig:
    default_space_id: str


class KBQueryAgent:
    def __init__(
        self,
        *,
        rag_backend: RagBackend,
        structured_backend: StructuredBackend,
        analytics_engine: KnowledgeAnalyticsEngine,
        config: KBQueryAgentConfig,
    ):
        self.rag_backend = rag_backend
        self.structured_backend = structured_backend
        self.analytics_engine = analytics_engine
        self.config = config

    async def retrieve(self, query: KnowledgeQuery) -> RetrievalResult:
        structured_records = await self.analytics_engine.query(query)
        if structured_records:
            return RetrievalResult(structured_records=structured_records, chunks=[])
        search_space_id = query.space_id or self._space_from_records(structured_records) or self.config.default_space_id
        page_matches = await self._query_page_title_matches(query.question, search_space_id)
        chunks = await self.rag_backend.search(
            query=query.question,
            dataset_id=search_space_id,
            filters={**query.filters, "space_id": search_space_id},
            top_k=query.top_k,
        )
        return RetrievalResult(
            structured_records=[*structured_records, *page_matches],
            chunks=chunks,
        )

    async def _query_page_title_matches(self, question: str, space_id: str) -> list[StructuredRecord]:
        pages = await self.structured_backend.list_items(
            "kb_pages",
            filters={
                "_and": [
                    {"space_id": {"_eq": space_id}},
                    {"status": {"_eq": "active"}},
                ]
            },
            fields=["id", "title", "canonical_url", "published_at", "content_hash"],
            limit=300,
        )
        matched: list[StructuredRecord] = []
        normalized_question = question.replace(" ", "")
        for page in pages:
            title = str(page.get("title") or "").strip()
            source = str(page.get("canonical_url") or "").strip()
            compact_title = title.replace(" ", "")
            if len(compact_title) < 3 or compact_title not in normalized_question or is_site_entry_url(source):
                continue
            matched.append(
                StructuredRecord(
                    collection="kb_pages",
                    data=page,
                    citation=Citation(
                        title=title,
                        source=source,
                        published_at=optional_text(page.get("published_at")),
                        metadata={"collection": "kb_pages", "id": page.get("id")},
                    ),
                    score=1.0,
                )
            )
        matched.sort(key=lambda record: len(str(record.data.get("title") or "")), reverse=True)
        return matched[:5]

    def _space_from_records(self, records: list[StructuredRecord]) -> str | None:
        for record in records:
            space_id = optional_text(record.data.get("space_id"))
            if space_id:
                return space_id
        return None


def citation_from_item(item: dict[str, Any], collection: str) -> Citation:
    title = str(
        item.get("title")
        or item.get("source_document")
        or item.get("name")
        or item.get("major_name")
        or collection
    )
    source = str(item.get("source_url") or item.get("source_document") or item.get("id") or "")
    snippet = str(item.get("source_text") or "")
    return Citation(
        title=title,
        source=source,
        snippet=snippet[:500],
        published_at=optional_text(item.get("published_at") or item.get("year")),
        department=optional_text(item.get("source_department")),
        metadata={"collection": collection, "id": item.get("id")},
    )


def optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def is_site_entry_url(url: str) -> bool:
    path = urlparse(url).path.rstrip("/")
    return path in {"", "/index.htm", "/index.html"}
