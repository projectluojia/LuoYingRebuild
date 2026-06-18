from __future__ import annotations

import re
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
            "dataset_ids": [dataset_id] if dataset_id else [],
            "metadata_condition": self._metadata_condition(filters),
            "page": 1,
            "page_size": top_k,
            "top_k": top_k,
            "keyword": True,
            "highlight": False,
        }
        data = await self._request(payload)
        return self._parse_chunks(data)

    async def upload_text_document(
        self,
        *,
        dataset_id: str,
        name: str,
        text: str,
    ) -> list[dict[str, Any]]:
        if not self.configured:
            raise BackendUnavailable("RAGFlow 未配置")
        safe_name = self._safe_file_name(name)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        files = {
            "file": (
                safe_name,
                text.encode("utf-8"),
                "text/plain",
            )
        }
        path = f"/api/v1/datasets/{dataset_id}/documents"
        if self.client is not None:
            response = await self.client.post(
                f"{self.base_url}{path}",
                files=files,
                headers=headers,
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                response = await client.post(
                    f"{self.base_url}{path}",
                    files=files,
                    headers=headers,
                )
        payload = self._json_response(response, "RAGFlow 文档上传失败")
        data = payload.get("data", [])
        return [dict(item) for item in data if isinstance(item, dict)]

    async def parse_documents(
        self,
        *,
        dataset_id: str,
        document_ids: list[str],
    ) -> None:
        if not document_ids:
            return
        payload = {"document_ids": document_ids}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        path = f"/api/v1/datasets/{dataset_id}/chunks"
        if self.client is not None:
            response = await self.client.post(
                f"{self.base_url}{path}",
                json=payload,
                headers=headers,
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                response = await client.post(
                    f"{self.base_url}{path}",
                    json=payload,
                    headers=headers,
                )
        self._json_response(response, "RAGFlow 文档解析启动失败")

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

    def _json_response(self, response: httpx.Response, message: str) -> dict[str, Any]:
        if response.status_code >= 400:
            raise BackendUnavailable(f"{message}：{response.status_code} {response.text[:300]}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise BackendUnavailable(f"{message}：响应格式无效")
        if payload.get("code") not in (None, 0):
            raise BackendUnavailable(f"{message}：{payload.get('message') or payload.get('code')}")
        return payload

    def _parse_chunks(self, payload: dict[str, Any]) -> list[RetrievedChunk]:
        if payload.get("code") not in (None, 0):
            raise BackendUnavailable(f"RAGFlow 检索失败：{payload.get('message') or payload.get('code')}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise BackendUnavailable("RAGFlow 检索响应缺少 data")
        candidates = data.get("chunks")
        if not isinstance(candidates, list):
            raise BackendUnavailable("RAGFlow 检索响应缺少 data.chunks")

        chunks: list[RetrievedChunk] = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            text = str(item.get("content") or "").strip()
            if not text:
                continue
            front_matter = self._extract_front_matter(text)
            document_id = str(item.get("document_id") or "")
            title = front_matter.get("title") or str(item.get("document_keyword") or document_id)
            source = front_matter.get("source") or ""
            score = self._to_float(item.get("similarity") or 0.0)
            metadata = {
                "chunk_id": item.get("id"),
                "document_id": document_id,
                "dataset_id": item.get("dataset_id"),
                "similarity": item.get("similarity"),
                "term_similarity": item.get("term_similarity"),
                "vector_similarity": item.get("vector_similarity"),
                "document_keyword": item.get("document_keyword"),
                "important_keywords": item.get("important_keywords"),
                "positions": item.get("positions"),
                "row_id": item.get("row_id"),
                "image_id": item.get("image_id"),
                "doc_type_kwd": item.get("doc_type_kwd"),
                "tag_kwd": item.get("tag_kwd"),
                "mom_id": item.get("mom_id"),
            }
            metadata = {key: value for key, value in metadata.items() if value not in (None, "", [])}
            citation = Citation(
                title=title,
                source=source,
                snippet=text[:500],
                published_at=self._to_optional_text(front_matter.get("published_at")),
                department=None,
                metadata=metadata,
            )
            chunks.append(RetrievedChunk(text=text, score=score, citation=citation, metadata=item))
        return chunks

    def _extract_front_matter(self, text: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for line in text.splitlines()[:8]:
            clean = line.strip()
            for key, target in (
                ("标题", "title"),
                ("来源", "source"),
                ("发布日期", "published_at"),
            ):
                prefix = f"{key}:"
                alt_prefix = f"{key}："
                if clean.startswith(prefix):
                    result[target] = clean[len(prefix):].strip()
                elif clean.startswith(alt_prefix):
                    result[target] = clean[len(alt_prefix):].strip()
        if result.get("published_at") == "未知":
            result.pop("published_at", None)
        return result

    def _to_float(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _to_optional_text(self, value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    def _metadata_condition(self, filters: dict[str, Any]) -> dict[str, Any] | None:
        conditions = []
        for key, value in filters.items():
            if value in (None, "", [], {}):
                continue
            conditions.append(
                {
                    "name": str(key),
                    "comparison_operator": "=",
                    "value": str(value),
                }
            )
        if not conditions:
            return None
        return {"logic": "and", "conditions": conditions}

    def _safe_file_name(self, name: str) -> str:
        clean = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", name).strip("._-")
        if not clean:
            clean = "knowledge_page"
        if not clean.lower().endswith(".txt"):
            clean += ".txt"
        return clean[:160]
