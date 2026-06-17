from __future__ import annotations

from typing import Any

import httpx

from luoying_bot.capabilities.knowledge_base.errors import BackendUnavailable
from luoying_bot.capabilities.knowledge_base.models import Citation, RetrievedChunk
from luoying_bot.capabilities.knowledge_base.ports import RagBackend


class RagflowClient(RagBackend):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        search_path: str = "/api/v1/retrieval",
        timeout_sec: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.search_path = search_path if search_path.startswith("/") else f"/{search_path}"
        self.timeout_sec = timeout_sec
        self.client = client

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    async def search(
        self,
        *,
        query: str,
        dataset_id: str,
        filters: dict[str, Any],
        top_k: int,
    ) -> list[RetrievedChunk]:
        if not self.configured:
            raise BackendUnavailable("RAGFlow 未配置")
        payload = {
            "question": query,
            "query": query,
            "dataset_id": dataset_id,
            "dataset_ids": [dataset_id] if dataset_id else [],
            "filters": filters,
            "top_k": top_k,
        }
        data = await self._request(payload)
        return self._parse_chunks(data)

    async def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if self.client is not None:
            response = await self.client.post(
                f"{self.base_url}{self.search_path}",
                json=payload,
                headers=headers,
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                response = await client.post(
                    f"{self.base_url}{self.search_path}",
                    json=payload,
                    headers=headers,
                )
        if response.status_code >= 400:
            raise BackendUnavailable(
                f"RAGFlow 请求失败：{response.status_code} {response.text[:300]}"
            )
        result = response.json()
        return dict(result) if isinstance(result, dict) else {}

    def _parse_chunks(self, payload: dict[str, Any]) -> list[RetrievedChunk]:
        containers: list[Any] = [
            payload.get("data"),
            payload,
        ]
        candidates: list[Any] = []
        for container in containers:
            if isinstance(container, dict):
                for key in ("chunks", "results", "documents", "items"):
                    value = container.get(key)
                    if isinstance(value, list):
                        candidates = value
                        break
            if candidates:
                break
        chunks: list[RetrievedChunk] = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            text = str(
                item.get("content")
                or item.get("text")
                or item.get("chunk")
                or item.get("document")
                or ""
            ).strip()
            if not text:
                continue
            title = str(
                item.get("document_name")
                or item.get("doc_name")
                or item.get("title")
                or item.get("filename")
                or "RAGFlow 文档"
            )
            source = str(
                item.get("url")
                or item.get("source")
                or item.get("document_id")
                or item.get("doc_id")
                or ""
            )
            score = self._to_float(item.get("score") or item.get("similarity") or 0.0)
            citation = Citation(
                title=title,
                source=source,
                snippet=text[:500],
                published_at=self._to_optional_text(item.get("published_at")),
                department=self._to_optional_text(item.get("department")),
                metadata={k: v for k, v in item.items() if k not in {"content", "text", "chunk"}},
            )
            chunks.append(RetrievedChunk(text=text, score=score, citation=citation, metadata=item))
        return chunks

    def _to_float(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _to_optional_text(self, value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

