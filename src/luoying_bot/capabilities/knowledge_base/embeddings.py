from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

import httpx

from luoying_bot.capabilities.knowledge_base.errors import BackendUnavailable


class EmbeddingProvider(Protocol):
    provider_id: str
    model: str

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


@dataclass(slots=True)
class OpenAICompatibleEmbeddingProvider:
    base_url: str
    api_key: str
    model: str
    batch_size: int = 32
    timeout_sec: float = 60.0
    provider_id: str = "openai-compatible"

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        clean_texts = [text.strip() for text in texts]
        if any(not text for text in clean_texts):
            raise BackendUnavailable("embedding input cannot be empty")
        embeddings: list[list[float]] = []
        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            for index in range(0, len(clean_texts), self.batch_size):
                batch = clean_texts[index : index + self.batch_size]
                response = await client.post(
                    self._embeddings_url(),
                    headers=self._headers(),
                    json={"model": self.model, "input": batch},
                )
                if response.status_code >= 400:
                    raise BackendUnavailable(
                        f"embedding endpoint failed: {response.status_code} {response.text[:300]}"
                    )
                payload = response.json()
                rows = payload.get("data")
                if not isinstance(rows, list) or len(rows) != len(batch):
                    raise BackendUnavailable("embedding endpoint returned invalid data shape")
                rows.sort(key=lambda item: int(item.get("index", 0)))
                for row in rows:
                    vector = row.get("embedding")
                    if not isinstance(vector, list) or not vector:
                        raise BackendUnavailable("embedding endpoint returned an empty vector")
                    embeddings.append(normalize_vector([float(value) for value in vector]))
        return embeddings

    def _embeddings_url(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/embeddings"):
            return base
        return f"{base}/embeddings"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers


def normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 8) for value in vector]
