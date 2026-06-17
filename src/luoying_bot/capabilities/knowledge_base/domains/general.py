from __future__ import annotations

from typing import Any

from luoying_bot.capabilities.knowledge_base.models import KnowledgeAnswer, KnowledgeQuery, StructuredRecord
from luoying_bot.capabilities.knowledge_base.ports import KnowledgeDomain, StructuredBackend


class GeneralKnowledgeDomain(KnowledgeDomain):
    name = "general"

    def __init__(self, *, default_dataset_id: str):
        self.default_dataset_id = default_dataset_id

    def dataset_id_for_space(self, space_id: str) -> str:
        return self.default_dataset_id or space_id

    def extract_filters(self, question: str, provided: dict[str, Any]) -> dict[str, Any]:
        return dict(provided)

    async def query_structured(
        self,
        backend: StructuredBackend,
        query: KnowledgeQuery,
    ) -> list[StructuredRecord]:
        return []

    def build_system_instruction(self, query: KnowledgeQuery) -> str:
        return "基于学校知识库资料回答。"

    def validate_answer(self, answer: KnowledgeAnswer) -> KnowledgeAnswer:
        return answer

