from __future__ import annotations

from luoying_bot.capabilities.knowledge_base.errors import BackendUnavailable
from luoying_bot.capabilities.knowledge_base.models import KnowledgeAnswer, RetrievalResult


NO_SOURCE_TEXT = (
    "当前知识库未收录该问题的可靠材料，暂不能给出确定回答。"
    "建议以学校或学院官网、正式公告和负责老师最新答复为准。"
)


class KnowledgeBasePolicy:
    def __init__(
        self,
        *,
        require_citation: bool = True,
        min_relevance: float = 0.5,
        min_rerank_score: float = 30.0,
    ):
        self.require_citation = require_citation
        # Structured (analytics) records bypass relevance gates because they come from
        # filtered SQL, not fuzzy similarity. Chunk-only evidence must pass the reranker
        # floor first, then the vector floor as a secondary distance guard.
        self.min_relevance = min_relevance
        self.min_rerank_score = min_rerank_score

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

        Only applies when there are no structured records (which are trusted). Every
        returned chunk must have passed the required reranker. If the best reranked chunk
        is still below the floor, the evidence is not answerable even when dense vector
        similarity is high.
        """
        if retrieval.structured_records or not retrieval.chunks:
            return False
        rerank_scores: list[float] = []
        for chunk in retrieval.chunks:
            if "rerank_score" not in (chunk.metadata or {}):
                raise BackendUnavailable("retrieved chunk is missing rerank_score")
            rerank_scores.append(float(chunk.metadata["rerank_score"]))
        if self.min_rerank_score > 0 and max(rerank_scores) < self.min_rerank_score:
            return True
        if self.min_relevance <= 0:
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
