from __future__ import annotations

from dataclasses import dataclass

from luoying_bot.capabilities.knowledge_base.analytics import KnowledgeAnalyticsEngine
from luoying_bot.capabilities.knowledge_base.entity_resolver import EntityResolver
from luoying_bot.capabilities.knowledge_base.entities import EntityMatch, normalize_entity_text
from luoying_bot.capabilities.knowledge_base.models import KnowledgeQuery, RetrievalResult, StructuredRecord
from luoying_bot.capabilities.knowledge_base.ports import RagBackend
from luoying_bot.capabilities.knowledge_base.text_utils import optional_text


@dataclass(slots=True)
class KBQueryAgentConfig:
    default_space_id: str


class KBQueryAgent:
    def __init__(
        self,
        *,
        rag_backend: RagBackend,
        analytics_engine: KnowledgeAnalyticsEngine,
        entity_resolver: EntityResolver,
        config: KBQueryAgentConfig,
    ):
        self.rag_backend = rag_backend
        self.analytics_engine = analytics_engine
        self.entity_resolver = entity_resolver
        self.config = config

    async def retrieve(self, query: KnowledgeQuery) -> RetrievalResult:
        entities = await self.entity_resolver.resolve(query)
        structured_records = await self.analytics_engine.query(query, entities)
        search_space_id = query.space_id or self._space_from_records(structured_records) or self.config.default_space_id
        chunks = await self.rag_backend.search(
            query=rag_query_with_entities(query.question, entities.matches),
            dataset_id=search_space_id,
            filters={**query.filters, "space_id": search_space_id},
            top_k=query.top_k,
        )
        return RetrievalResult(
            structured_records=structured_records,
            chunks=chunks,
        )

    def _space_from_records(self, records: list[StructuredRecord]) -> str | None:
        for record in records:
            space_id = optional_text(record.data.get("space_id"))
            if space_id:
                return space_id
        return None


def rag_query_with_entities(question: str, matches: tuple[EntityMatch, ...], *, max_terms: int = 24) -> str:
    terms: list[str] = []
    seen: set[str] = {normalize_entity_text(question)}
    for match in matches:
        if not should_expand_rag_query(match):
            continue
        for term in [match.canonical_name, match.matched_alias, *match.aliases]:
            clean_term = term.strip()
            normalized = normalize_entity_text(clean_term)
            if not clean_term or not normalized or normalized in seen:
                continue
            seen.add(normalized)
            terms.append(clean_term)
            if len(terms) >= max_terms:
                break
        if len(terms) >= max_terms:
            break
    if not terms:
        return question
    return f"{question}\n实体别名：{' '.join(terms)}"


def should_expand_rag_query(match: EntityMatch) -> bool:
    return match.score >= 100.0 or match.alias_type == "relation_resolution"
