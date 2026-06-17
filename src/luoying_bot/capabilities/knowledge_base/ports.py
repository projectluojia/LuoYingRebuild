from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from luoying_bot.capabilities.knowledge_base.models import (
    KnowledgeAnswer,
    KnowledgeQuery,
    RetrievedChunk,
    StructuredRecord,
)


class RagBackend(ABC):
    @abstractmethod
    async def search(
        self,
        *,
        query: str,
        dataset_id: str,
        filters: dict[str, Any],
        top_k: int,
    ) -> list[RetrievedChunk]: ...


class StructuredBackend(ABC):
    @abstractmethod
    async def list_items(
        self,
        collection: str,
        *,
        filters: dict[str, Any],
        fields: list[str] | None = None,
        limit: int = 20,
        sort: list[str] | None = None,
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def create_item(
        self,
        collection: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def update_item(
        self,
        collection: str,
        item_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...


class KnowledgeDomain(ABC):
    name: str

    @abstractmethod
    def dataset_id_for_space(self, space_id: str) -> str: ...

    @abstractmethod
    def extract_filters(self, question: str, provided: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    async def query_structured(
        self,
        backend: StructuredBackend,
        query: KnowledgeQuery,
    ) -> list[StructuredRecord]: ...

    @abstractmethod
    def build_system_instruction(self, query: KnowledgeQuery) -> str: ...

    @abstractmethod
    def validate_answer(self, answer: KnowledgeAnswer) -> KnowledgeAnswer: ...
