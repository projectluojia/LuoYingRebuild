from __future__ import annotations

from luoying_bot.capabilities.knowledge_base.models import KnowledgeAnswer, RetrievalResult


NO_SOURCE_TEXT = (
    "当前知识库未收录该问题的可靠材料，暂不能给出确定回答。"
    "建议以学校或学院官网、正式公告和负责老师最新答复为准。"
)


class KnowledgeBasePolicy:
    def __init__(self, *, require_citation: bool = True, min_relevance: float = 0.5):
        self.require_citation = require_citation
        # Minimum cosine similarity (``vector_score``) the top retrieved chunk must reach
        # before we trust chunk-only evidence. Structured (analytics) records bypass this
        # gate because they come from filtered SQL, not fuzzy similarity. Set to 0 to
        # disable the relevance floor entirely.
        self.min_relevance = min_relevance

    def fallback_for_missing_evidence(self) -> KnowledgeAnswer:
        return KnowledgeAnswer(
            answer=NO_SOURCE_TEXT,
            citations=[],
            confidence=0.0,
            fallback_reason="no_reliable_source",
        )

    def fallback_for_low_relevance(self) -> KnowledgeAnswer:
        return KnowledgeAnswer(
            answer=NO_SOURCE_TEXT,
            citations=[],
            confidence=0.0,
            fallback_reason="low_relevance",
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
        if self._is_low_relevance(retrieval):
            return self.fallback_for_low_relevance()
        return None

    def _is_low_relevance(self, retrieval: RetrievalResult) -> bool:
        """Refuse chunk-only answers whose strongest semantic match is too distant.

        Only applies when there are no structured records (which are trusted). We look at
        the best ``vector_score`` across the whole result set: if even the most
        semantically-similar chunk falls below the floor, nothing retrieved is relevant
        enough to answer from. Backends that do not expose ``vector_score`` are skipped.
        """
        if self.min_relevance <= 0 or retrieval.structured_records or not retrieval.chunks:
            return False
        vector_scores = [
            float(chunk.metadata["vector_score"])
            for chunk in retrieval.chunks
            if (chunk.metadata or {}).get("vector_score") is not None
        ]
        if not vector_scores:
            return False
        return max(vector_scores) < self.min_relevance

    def validate_answer(self, answer: KnowledgeAnswer) -> KnowledgeAnswer:
        if self.require_citation and not answer.citations:
            return self.fallback_for_missing_evidence()
        return answer

