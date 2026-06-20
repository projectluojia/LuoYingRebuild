from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class KnowledgeAnswerRequest(BaseModel):
    space_id: str | None = None
    question: str
    platform: str | None = None
    conversation_id: str | None = None
    user_id: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=8, ge=1, le=20)


class CitationResponse(BaseModel):
    title: str
    source: str
    snippet: str = ""
    published_at: str | None = None
    department: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeAnswerResponse(BaseModel):
    answer: str
    citations: list[CitationResponse]
    confidence: float
    need_follow_up: bool = False
    follow_up_question: str | None = None
    image_url: str | None = None
    fallback_reason: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSearchRequest(BaseModel):
    space_id: str | None = None
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=8, ge=1, le=20)


class KnowledgeFeedbackRequest(BaseModel):
    answer_log_id: str | None = None
    request_uid: str | None = None
    feedback_type: str
    comment: str = ""
    submitted_by: str | None = None


class DynamicQaRequest(BaseModel):
    space_id: str | None = None
    question: str
    answer: str
    submitted_by: str | None = None
    source_platform: str | None = None
    source_conversation_id: str | None = None
    source_message_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
