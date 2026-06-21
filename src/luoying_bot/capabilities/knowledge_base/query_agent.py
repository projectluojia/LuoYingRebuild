from __future__ import annotations

from luoying_bot.capabilities.knowledge_base.analytics import KnowledgeAnalyticsEngine
from luoying_bot.capabilities.knowledge_base.entity_resolver import EntityResolver
from luoying_bot.capabilities.knowledge_base.entities import GLOBAL_ENTITY_SPACE_ID, EntityMatch, normalize_entity_text
from luoying_bot.capabilities.knowledge_base.models import KnowledgeQuery, RetrievalResult, StructuredRecord
from luoying_bot.capabilities.knowledge_base.ports import RagBackend
from luoying_bot.capabilities.knowledge_base.text_utils import optional_text


class KBQueryAgent:
    def __init__(
        self,
        *,
        rag_backend: RagBackend,
        analytics_engine: KnowledgeAnalyticsEngine,
        entity_resolver: EntityResolver,
    ):
        self.rag_backend = rag_backend
        self.analytics_engine = analytics_engine
        self.entity_resolver = entity_resolver

    async def retrieve(self, query: KnowledgeQuery) -> RetrievalResult:
        entities = await self.entity_resolver.resolve(query)
        structured_records = await self.analytics_engine.query(query, entities)
        chunks = await self.rag_backend.search(
            queries=rag_query_routes(query.question, entities.matches),
            space_ids=self._search_space_ids(query, structured_records, entities.matches),
            top_k=query.top_k,
        )
        return RetrievalResult(
            structured_records=structured_records,
            chunks=chunks,
        )

    def _search_space_ids(
        self,
        query: KnowledgeQuery,
        records: list[StructuredRecord],
        matches: tuple[EntityMatch, ...],
    ) -> list[str]:
        if not optional_text(query.space_id):
            return []
        spaces: list[str] = []
        append_space(spaces, query.space_id)
        for match in matches:
            if should_expand_rag_query(match) and match.space_id != GLOBAL_ENTITY_SPACE_ID:
                append_space(spaces, match.space_id)
        for record in records:
            append_space(spaces, optional_text(record.data.get("space_id")))
        return spaces


def rag_query_routes(question: str, matches: tuple[EntityMatch, ...], *, max_terms: int = 24) -> list[str]:
    routes = [question]
    expanded = expanded_rag_query(question, matches, max_terms=max_terms)
    if normalize_entity_text(expanded) != normalize_entity_text(question):
        routes.append(expanded)
    return routes


def expanded_rag_query(question: str, matches: tuple[EntityMatch, ...], *, max_terms: int = 24) -> str:
    terms: list[str] = []
    question_norm = normalize_entity_text(question)
    seen: set[str] = {question_norm}
    for match in matches:
        if not should_expand_rag_query(match):
            continue
        canonical_norm = normalize_entity_text(match.canonical_name)
        if canonical_norm and canonical_norm in question_norm:
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


def append_space(spaces: list[str], space_id: str | None) -> None:
    clean_space_id = optional_text(space_id)
    if clean_space_id and clean_space_id not in spaces:
        spaces.append(clean_space_id)
