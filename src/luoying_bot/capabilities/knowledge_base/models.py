from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Citation:
    title: str
    source: str
    snippet: str = ""
    published_at: str | None = None
    department: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def label(self) -> str:
        parts = [self.title.strip() or "未命名来源"]
        if self.department:
            parts.append(self.department)
        if self.published_at:
            parts.append(self.published_at)
        if self.source:
            parts.append(self.source)
        return "，".join(parts)

    def link_label(self) -> str:
        if not self.source:
            return self.label()
        parts = [self.title.strip() or "未命名来源"]
        if self.department:
            parts.append(self.department)
        if self.published_at:
            parts.append(self.published_at)
        return f"{self.source}（{'，'.join(parts)}）"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "source": self.source,
            "snippet": self.snippet,
            "published_at": self.published_at,
            "department": self.department,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class RetrievedChunk:
    text: str
    score: float = 0.0
    citation: Citation | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "score": self.score,
            "citation": self.citation.to_dict() if self.citation else None,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class StructuredRecord:
    collection: str
    data: dict[str, Any]
    citation: Citation | None = None
    score: float = 1.0

    def text(self) -> str:
        pairs = [
            f"{key}={value}"
            for key, value in self.data.items()
            if value not in (None, "", [], {})
        ]
        return f"{self.collection}: " + "；".join(pairs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "collection": self.collection,
            "data": self.data,
            "citation": self.citation.to_dict() if self.citation else None,
            "score": self.score,
        }


@dataclass(slots=True)
class KnowledgeQuery:
    question: str
    space_id: str
    platform: str = ""
    conversation_id: str = ""
    user_id: str = ""
    filters: dict[str, Any] = field(default_factory=dict)
    top_k: int = 8


@dataclass(slots=True)
class RetrievalResult:
    structured_records: list[StructuredRecord] = field(default_factory=list)
    chunks: list[RetrievedChunk] = field(default_factory=list)
    follow_up_question: str | None = None
    fallback_reason: str | None = None

    @property
    def has_evidence(self) -> bool:
        return bool(self.structured_records or self.chunks)

    def citations(self) -> list[Citation]:
        seen: set[tuple[str, str]] = set()
        citations: list[Citation] = []
        for citation in [
            *(record.citation for record in self.structured_records),
            *(chunk.citation for chunk in self.chunks),
        ]:
            if citation is None:
                continue
            key = (citation.title, citation.source)
            if key in seen:
                continue
            seen.add(key)
            citations.append(citation)
        return citations


@dataclass(slots=True)
class KnowledgeAnswer:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    confidence: float = 0.0
    need_follow_up: bool = False
    follow_up_question: str | None = None
    image_url: str | None = None
    fallback_reason: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def text_with_citations(self) -> str:
        text = self.answer.strip()
        if not self.citations:
            return text
        lines = [text, "", "来源："]
        for citation in self.citations:
            lines.append(f"- {citation.label()}")
        return "\n".join(lines).strip()

    def source_links_text(self) -> str:
        if not self.citations:
            return ""
        lines = ["来源链接："]
        for citation in self.citations:
            lines.append(citation.link_label())
        return "\n".join(lines).strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "citations": [citation.to_dict() for citation in self.citations],
            "confidence": self.confidence,
            "need_follow_up": self.need_follow_up,
            "follow_up_question": self.follow_up_question,
            "image_url": self.image_url,
            "fallback_reason": self.fallback_reason,
            "data": self.data,
        }
