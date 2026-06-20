from __future__ import annotations

from luoying_bot.capabilities.knowledge_base.models import Citation, RetrievedChunk, RetrievalResult, StructuredRecord
from luoying_bot.capabilities.knowledge_base.policy import NO_SOURCE_TEXT, KnowledgeBasePolicy


def _retrieval(*, chunks=None, records=None, follow_up=None):
    return RetrievalResult(
        structured_records=records or [],
        chunks=chunks or [],
        follow_up_question=follow_up,
    )


def _chunk(title="t", source="s"):
    return RetrievedChunk(text="x", citation=Citation(title=title, source=source))


class TestFallbackAnswers:
    def test_fallback_for_missing_evidence_shape(self):
        answer = KnowledgeBasePolicy().fallback_for_missing_evidence()
        assert answer.answer == NO_SOURCE_TEXT
        assert answer.citations == []
        assert answer.confidence == 0.0
        assert answer.fallback_reason == "no_reliable_source"

    def test_require_follow_up_shape(self):
        answer = KnowledgeBasePolicy().require_follow_up("还需要哪一年？")
        assert answer.answer == "还需要哪一年？"
        assert answer.need_follow_up is True
        assert answer.follow_up_question == "还需要哪一年？"
        assert answer.fallback_reason == "missing_required_filters"


class TestValidateRetrieval:
    def test_follow_up_question_takes_priority(self):
        policy = KnowledgeBasePolicy()
        result = _retrieval(chunks=[_chunk()], follow_up="请明确省份")
        answer = policy.validate_retrieval(result)
        assert answer is not None
        assert answer.need_follow_up is True

    def test_empty_retrieval_triggers_fallback(self):
        policy = KnowledgeBasePolicy()
        answer = policy.validate_retrieval(_retrieval())
        assert answer is not None
        assert answer.fallback_reason == "no_reliable_source"

    def test_evidence_without_citations_triggers_fallback_when_required(self):
        policy = KnowledgeBasePolicy(require_citation=True)
        # chunks present but none carry a citation
        result = _retrieval(chunks=[RetrievedChunk(text="x", citation=None)])
        answer = policy.validate_retrieval(result)
        assert answer is not None
        assert answer.fallback_reason == "no_reliable_source"

    def test_evidence_without_citations_passes_when_not_required(self):
        policy = KnowledgeBasePolicy(require_citation=False)
        result = _retrieval(chunks=[RetrievedChunk(text="x", citation=None)])
        assert policy.validate_retrieval(result) is None

    def test_structured_record_without_citation_triggers_fallback(self):
        policy = KnowledgeBasePolicy(require_citation=True)
        result = _retrieval(records=[StructuredRecord(collection="c", data={"x": 1})])
        answer = policy.validate_retrieval(result)
        assert answer is not None

    def test_full_evidence_returns_none(self):
        policy = KnowledgeBasePolicy()
        result = _retrieval(chunks=[_chunk()])
        assert policy.validate_retrieval(result) is None


class TestValidateAnswer:
    def test_answer_without_citations_replaced_when_required(self):
        from luoying_bot.capabilities.knowledge_base.models import KnowledgeAnswer

        policy = KnowledgeBasePolicy(require_citation=True)
        answer = KnowledgeAnswer(answer="hi", citations=[])
        validated = policy.validate_answer(answer)
        assert validated.fallback_reason == "no_reliable_source"

    def test_answer_with_citations_passes_through(self):
        from luoying_bot.capabilities.knowledge_base.models import KnowledgeAnswer

        policy = KnowledgeBasePolicy()
        answer = KnowledgeAnswer(answer="hi", citations=[Citation(title="t", source="s")])
        assert policy.validate_answer(answer) is answer


def _vec_chunk(vector_score: float, score: float = 1.0) -> RetrievedChunk:
    return RetrievedChunk(
        text="x",
        score=score,
        citation=Citation(title="t", source="s"),
        metadata={"vector_score": vector_score},
    )


class TestRelevanceThreshold:
    def test_low_relevance_chunk_only_falls_back(self):
        policy = KnowledgeBasePolicy(min_relevance=0.5)
        result = _retrieval(chunks=[_vec_chunk(0.4)])
        answer = policy.validate_retrieval(result)
        assert answer is not None
        assert answer.fallback_reason == "low_relevance"

    def test_high_relevance_chunk_only_passes(self):
        policy = KnowledgeBasePolicy(min_relevance=0.5)
        assert policy.validate_retrieval(_retrieval(chunks=[_vec_chunk(0.7)])) is None

    def test_structured_records_bypass_threshold(self):
        # analytics records are trusted; a low-relevance chunk must NOT trigger fallback.
        policy = KnowledgeBasePolicy(min_relevance=0.5)
        result = _retrieval(
            records=[StructuredRecord(collection="c", data={"x": 1})],
            chunks=[_vec_chunk(0.1)],
        )
        assert policy.validate_retrieval(result) is None

    def test_threshold_disabled_when_zero(self):
        policy = KnowledgeBasePolicy(min_relevance=0.0)
        assert policy.validate_retrieval(_retrieval(chunks=[_vec_chunk(0.1)])) is None

    def test_uses_best_vector_score_across_chunks(self):
        # the relevance signal is the best vector_score in the result set, not the
        # highest-combined-score chunk: one strongly-similar chunk is enough to answer.
        policy = KnowledgeBasePolicy(min_relevance=0.5)
        mixed = _retrieval(chunks=[_vec_chunk(0.3, score=2.0), _vec_chunk(0.9, score=0.5)])
        assert policy.validate_retrieval(mixed) is None  # best vector 0.9 >= 0.5
        all_low = _retrieval(chunks=[_vec_chunk(0.3, score=2.0), _vec_chunk(0.4, score=1.0)])
        answer = policy.validate_retrieval(all_low)
        assert answer is not None
        assert answer.fallback_reason == "low_relevance"

    def test_missing_vector_score_skips_threshold(self):
        policy = KnowledgeBasePolicy(min_relevance=0.5)
        result = _retrieval(chunks=[RetrievedChunk(text="x", citation=Citation(title="t", source="s"))])
        assert policy.validate_retrieval(result) is None
