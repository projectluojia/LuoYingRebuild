from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from luoying_bot.capabilities.knowledge_base.text_utils import (
    longest_common_substring_length,
    normalize_alnum_text,
)

# Backwards-compatible alias: other modules import ``normalize_entity_text`` from here.
normalize_entity_text = normalize_alnum_text


@dataclass(frozen=True, slots=True)
class EntityMatch:
    entity_id: str
    space_id: str
    entity_type: str
    canonical_name: str
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    matched_alias: str = ""
    alias_type: str = ""
    score: float = 0.0
    confidence: float = 0.0

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "EntityMatch":
        metadata = parse_metadata(row.get("metadata_json") or row.get("metadata") or {})
        return cls(
            entity_id=str(row["entity_id"]),
            space_id=str(row["space_id"]),
            entity_type=str(row["entity_type"]),
            canonical_name=str(row["canonical_name"]),
            description=str(row.get("description") or ""),
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
            matched_alias=str(row.get("matched_alias") or row.get("alias") or ""),
            alias_type=str(row.get("alias_type") or ""),
            score=float(row.get("score") or 0.0),
            confidence=float(row.get("confidence") or 0.0),
        )

    def prompt_line(self) -> str:
        metadata_text = ", ".join(
            f"{key}={value}" for key, value in sorted(self.metadata.items()) if value not in (None, "", [], {})
        )
        parts = [
            f"type={self.entity_type}",
            f"name={self.canonical_name}",
            f"matched_alias={self.matched_alias or self.canonical_name}",
            f"confidence={self.confidence:.2f}",
        ]
        if metadata_text:
            parts.append(f"metadata: {metadata_text}")
        return "; ".join(parts)


def stable_entity_id(space_id: str, entity_type: str, canonical_name: str) -> str:
    raw = f"{space_id}:{entity_type}:{normalize_entity_text(canonical_name)}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{space_id}_{entity_type}_{digest}"


def stable_search_item_id(space_id: str, item_type: str, source_key: str) -> str:
    raw = f"{space_id}:{item_type}:{source_key}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
    return f"{space_id}_{item_type}_{digest}"


def parse_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def entity_match_score(*, query_norm: str, alias_norm: str, canonical_norm: str) -> float:
    if not query_norm or not alias_norm:
        return 0.0
    if alias_norm in query_norm:
        return 100.0 + min(len(alias_norm), 30)
    if canonical_norm and canonical_norm in query_norm:
        return 92.0 + min(len(canonical_norm), 30)
    overlap = max(
        longest_common_substring_length(alias_norm, query_norm),
        longest_common_substring_length(canonical_norm, query_norm) if canonical_norm else 0,
    )
    threshold = 2 if len(alias_norm) <= 3 else 3
    if overlap < threshold:
        return 0.0
    coverage = overlap / max(len(alias_norm), 1)
    return 35.0 + 40.0 * coverage
