from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from luoying_bot.capabilities.knowledge_base.answering import KnowledgeAnswerGenerator
from luoying_bot.capabilities.knowledge_base.errors import BackendUnavailable, KnowledgeBaseError
from luoying_bot.capabilities.knowledge_base.models import (
    KnowledgeAnswer,
    KnowledgeQuery,
    RetrievalResult,
)
from luoying_bot.capabilities.knowledge_base.policy import KnowledgeBasePolicy
from luoying_bot.capabilities.knowledge_base.ports import StructuredBackend
from luoying_bot.capabilities.knowledge_base.query_agent import KBQueryAgent

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class KnowledgeBaseConfig:
    default_space_id: str
    require_citation: bool = True


class KnowledgeBaseService:
    def __init__(
        self,
        *,
        structured_backend: StructuredBackend,
        query_agent: KBQueryAgent,
        answer_generator: KnowledgeAnswerGenerator,
        config: KnowledgeBaseConfig,
        policy: KnowledgeBasePolicy | None = None,
    ):
        self.structured_backend = structured_backend
        self.query_agent = query_agent
        self.answer_generator = answer_generator
        self.config = config
        self.policy = policy or KnowledgeBasePolicy(require_citation=config.require_citation)

    async def answer(
        self,
        *,
        question: str,
        space_id: str | None = None,
        platform: str = "",
        conversation_id: str = "",
        user_id: str = "",
        filters: dict[str, Any] | None = None,
        top_k: int = 8,
        request_uid: str | None = None,
    ) -> KnowledgeAnswer:
        query = self._build_query(
            question=question,
            space_id=space_id,
            platform=platform,
            conversation_id=conversation_id,
            user_id=user_id,
            filters=filters,
            top_k=top_k,
        )
        retrieval = await self._retrieve(query)
        policy_answer = self.policy.validate_retrieval(retrieval)
        if policy_answer is not None:
            await self._record_answer_log(
                query=query,
                answer=policy_answer,
                retrieval=retrieval,
                request_uid=request_uid,
            )
            return policy_answer

        answer = await self.answer_generator.generate(query, retrieval)
        answer = self.policy.validate_answer(answer)
        await self._record_answer_log(
            query=query,
            answer=answer,
            retrieval=retrieval,
            request_uid=request_uid,
        )
        return answer

    async def search(
        self,
        *,
        query_text: str,
        space_id: str | None = None,
        filters: dict[str, Any] | None = None,
        top_k: int = 8,
    ) -> RetrievalResult:
        query = self._build_query(
            question=query_text,
            space_id=space_id,
            filters=filters,
            top_k=top_k,
        )
        return await self._retrieve(query)

    async def submit_dynamic_qa(
        self,
        *,
        question: str,
        answer: str,
        space_id: str | None = None,
        submitted_by: str = "",
        source_platform: str = "",
        source_conversation_id: str = "",
        source_message_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "space_id": space_id or self.config.default_space_id,
            "question": question.strip(),
            "answer": answer.strip(),
            "submitted_by": submitted_by,
            "source_platform": source_platform,
            "source_conversation_id": source_conversation_id,
            "source_message_id": source_message_id,
            "review_status": "pending",
            "metadata": metadata or {},
            "created_at": self._now_iso(),
        }
        if not payload["question"] or not payload["answer"]:
            raise KnowledgeBaseError("动态问答的问题和答案不能为空")
        return await self.structured_backend.create_item("dynamic_qa", payload)

    async def submit_feedback(
        self,
        *,
        feedback_type: str,
        answer_log_id: str | None = None,
        request_uid: str | None = None,
        comment: str = "",
        submitted_by: str = "",
    ) -> dict[str, Any]:
        payload = {
            "answer_log_id": answer_log_id,
            "request_uid": request_uid,
            "feedback_type": feedback_type,
            "comment": comment,
            "submitted_by": submitted_by,
            "status": "open",
            "created_at": self._now_iso(),
        }
        return await self.structured_backend.create_item("kb_feedback", payload)

    async def _retrieve(self, query: KnowledgeQuery) -> RetrievalResult:
        try:
            return await self.query_agent.retrieve(query)
        except BackendUnavailable as exc:
            logger.warning("知识库子 agent 查询失败：%s", exc)
            return RetrievalResult(fallback_reason=str(exc))

    async def _record_answer_log(
        self,
        *,
        query: KnowledgeQuery,
        answer: KnowledgeAnswer,
        retrieval: RetrievalResult,
        request_uid: str | None,
    ) -> None:
        payload = {
            "request_uid": request_uid or uuid.uuid4().hex,
            "space_id": query.space_id,
            "platform": query.platform,
            "conversation_id": query.conversation_id,
            "user_id": query.user_id,
            "question": query.question,
            "filters": query.filters,
            "structured_records": [record.to_dict() for record in retrieval.structured_records],
            "retrieved_chunks": [chunk.to_dict() for chunk in retrieval.chunks],
            "citations": [citation.to_dict() for citation in answer.citations],
            "answer": answer.answer,
            "confidence": answer.confidence,
            "fallback_reason": answer.fallback_reason or retrieval.fallback_reason,
            "created_at": self._now_iso(),
        }
        try:
            await self.structured_backend.create_item("kb_answer_logs", payload)
        except BackendUnavailable as exc:
            logger.warning("问答日志写入失败：%s", exc)

    def _build_query(
        self,
        *,
        question: str,
        space_id: str | None = None,
        platform: str = "",
        conversation_id: str = "",
        user_id: str = "",
        filters: dict[str, Any] | None = None,
        top_k: int = 8,
    ) -> KnowledgeQuery:
        clean_question = question.strip()
        if not clean_question:
            raise KnowledgeBaseError("知识库问题不能为空")
        clean_space_id = str(space_id or "").strip() or self.config.default_space_id
        return KnowledgeQuery(
            question=clean_question,
            space_id=clean_space_id,
            platform=platform,
            conversation_id=conversation_id,
            user_id=user_id,
            filters=filters or {},
            top_k=top_k,
        )

    def _now_iso(self) -> str:
        return datetime.now().isoformat(timespec="seconds")
