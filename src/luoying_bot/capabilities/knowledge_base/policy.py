from __future__ import annotations

from luoying_bot.capabilities.knowledge_base.models import KnowledgeAnswer, RetrievalResult


NO_SOURCE_TEXT = (
    "当前知识库未收录该问题的可靠材料，暂不能给出确定回答。"
    "建议以学校或学院官网、正式公告和负责老师最新答复为准。"
)


class KnowledgeBasePolicy:
    def __init__(self, *, require_citation: bool = True):
        self.require_citation = require_citation

    def fallback_for_missing_evidence(self) -> KnowledgeAnswer:
        return KnowledgeAnswer(
            answer=NO_SOURCE_TEXT,
            citations=[],
            confidence=0.0,
            fallback_reason="no_reliable_source",
        )

    def require_follow_up(self, question: str) -> KnowledgeAnswer:
        return KnowledgeAnswer(
            answer=question,
            citations=[],
            confidence=0.0,
            need_follow_up=True,
            follow_up_question=question,
            fallback_reason="missing_required_filters",
        )

    def validate_retrieval(self, retrieval: RetrievalResult) -> KnowledgeAnswer | None:
        if retrieval.follow_up_question:
            return self.require_follow_up(retrieval.follow_up_question)
        if not retrieval.has_evidence:
            return self.fallback_for_missing_evidence()
        if self.require_citation and not retrieval.citations():
            return self.fallback_for_missing_evidence()
        return None

    def validate_answer(self, answer: KnowledgeAnswer) -> KnowledgeAnswer:
        if self.require_citation and not answer.citations:
            return self.fallback_for_missing_evidence()
        return answer

