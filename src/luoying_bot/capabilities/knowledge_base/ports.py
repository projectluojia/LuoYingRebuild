from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from luoying_bot.capabilities.knowledge_base.models import (
    RetrievedChunk,
)


class RagBackend(ABC):
    @abstractmethod
    async def search(
        self,
        *,
        queries: list[str],
        space_ids: list[str],
        top_k: int,
    ) -> list[RetrievedChunk]: ...


class AnalyticsBackend(ABC):
    @abstractmethod
    async def execute_select(
        self,
        sql: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]: ...


class EntityBackend(ABC):
    @abstractmethod
    async def search_kb_items(
        self,
        *,
        query: str,
        space_id: str,
        item_types: list[str] | None = None,
        limit: int = 12,
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def fetch_entity_relations(
        self,
        *,
        space_id: str,
        entity_ids: list[str],
    ) -> list[dict[str, Any]]: ...


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

    @abstractmethod
    async def distinct_values(
        self,
        collection: str,
        field: str,
        *,
        filters: dict[str, Any] | None = None,
        limit: int = 10000,
    ) -> list[str]: ...
