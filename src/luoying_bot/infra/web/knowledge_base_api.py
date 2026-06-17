from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException

from luoying_bot.capabilities.knowledge_base.errors import KnowledgeBaseError
from luoying_bot.capabilities.knowledge_base.schemas import (
    CitationResponse,
    DynamicQaRequest,
    KnowledgeAnswerRequest,
    KnowledgeAnswerResponse,
    KnowledgeFeedbackRequest,
    KnowledgeSearchRequest,
)

if TYPE_CHECKING:
    from luoying_bot.bootstrap import AppContainer


def create_knowledge_base_router(
    *,
    container_provider: Callable[[], "AppContainer"],
    current_user_dependency: Callable[..., Any],
) -> APIRouter:
    router = APIRouter(prefix="/knowledge", tags=["knowledge"])

    @router.post("/answer", response_model=KnowledgeAnswerResponse)
    async def answer(
        req: KnowledgeAnswerRequest,
        user=Depends(current_user_dependency),
    ) -> KnowledgeAnswerResponse:
        try:
            result = await container_provider().services.knowledge_base_service.answer(
                question=req.question,
                space_id=req.space_id,
                domain=req.domain,
                platform=req.platform or "web",
                conversation_id=req.conversation_id or "web-knowledge",
                user_id=req.user_id or user.user_id,
                filters=req.filters,
                top_k=req.top_k,
            )
        except KnowledgeBaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _answer_response(result.to_dict())

    @router.post("/search")
    async def search(
        req: KnowledgeSearchRequest,
        user=Depends(current_user_dependency),
    ) -> dict[str, Any]:
        try:
            result = await container_provider().services.knowledge_base_service.search(
                query_text=req.query,
                space_id=req.space_id,
                domain=req.domain,
                filters=req.filters,
                top_k=req.top_k,
            )
        except KnowledgeBaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "structured_records": [record.to_dict() for record in result.structured_records],
            "chunks": [chunk.to_dict() for chunk in result.chunks],
            "citations": [citation.to_dict() for citation in result.citations()],
            "fallback_reason": result.fallback_reason,
            "user_id": user.user_id,
        }

    @router.post("/dynamic-qa")
    async def submit_dynamic_qa(
        req: DynamicQaRequest,
        user=Depends(current_user_dependency),
    ) -> dict[str, Any]:
        try:
            result = await container_provider().services.knowledge_base_service.submit_dynamic_qa(
                question=req.question,
                answer=req.answer,
                space_id=req.space_id,
                submitted_by=req.submitted_by or user.user_id,
                source_platform=req.source_platform or "web",
                source_conversation_id=req.source_conversation_id or "",
                source_message_id=req.source_message_id or "",
                metadata=req.metadata,
            )
        except KnowledgeBaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": result}

    @router.post("/feedback")
    async def submit_feedback(
        req: KnowledgeFeedbackRequest,
        user=Depends(current_user_dependency),
    ) -> dict[str, Any]:
        try:
            result = await container_provider().services.knowledge_base_service.submit_feedback(
                feedback_type=req.feedback_type,
                answer_log_id=req.answer_log_id,
                request_uid=req.request_uid,
                comment=req.comment,
                submitted_by=req.submitted_by or user.user_id,
            )
        except KnowledgeBaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": result}

    return router


def _answer_response(data: dict[str, Any]) -> KnowledgeAnswerResponse:
    return KnowledgeAnswerResponse(
        answer=str(data.get("answer") or ""),
        citations=[
            CitationResponse(**citation)
            for citation in data.get("citations", [])
            if isinstance(citation, dict)
        ],
        confidence=float(data.get("confidence") or 0.0),
        need_follow_up=bool(data.get("need_follow_up")),
        follow_up_question=data.get("follow_up_question"),
        image_url=data.get("image_url"),
        fallback_reason=data.get("fallback_reason"),
        data=dict(data.get("data") or {}),
    )
