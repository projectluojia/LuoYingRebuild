from __future__ import annotations

from luoying_bot.capabilities.knowledge_base.models import KnowledgeQuery, RetrievalResult
from luoying_bot.capabilities.knowledge_base.ports import KnowledgeDomain, RagBackend, StructuredBackend


class KnowledgeRetriever:
    def __init__(
        self,
        *,
        rag_backend: RagBackend,
        structured_backend: StructuredBackend,
        domain: KnowledgeDomain,
    ):
        self.rag_backend = rag_backend
        self.structured_backend = structured_backend
        self.domain = domain

    async def retrieve(self, query: KnowledgeQuery) -> RetrievalResult:
        filters = self.domain.extract_filters(query.question, query.filters)
        hydrated = KnowledgeQuery(
            question=query.question,
            space_id=query.space_id,
            domain=query.domain,
            platform=query.platform,
            conversation_id=query.conversation_id,
            user_id=query.user_id,
            filters=filters,
            top_k=query.top_k,
        )
        structured = await self.domain.query_structured(self.structured_backend, hydrated)
        dataset_id = self.domain.dataset_id_for_space(hydrated.space_id)
        chunks = await self.rag_backend.search(
            query=hydrated.question,
            dataset_id=dataset_id,
            filters=filters,
            top_k=hydrated.top_k,
        )
        return RetrievalResult(structured_records=structured, chunks=chunks)

