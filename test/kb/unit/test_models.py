from __future__ import annotations

import pytest

from luoying_bot.capabilities.knowledge_base.models import (
    Citation,
    KnowledgeAnswer,
    RetrievedChunk,
    RetrievalResult,
    StructuredRecord,
)


class TestCitation:
    def test_label_joins_all_present_parts(self):
        citation = Citation(
            title="计算机学院",
            source="https://example.test/cs",
            published_at="2024-06-01",
            department="人工智能学院",
        )
        assert citation.label() == "计算机学院，人工智能学院，2024-06-01，https://example.test/cs"

    def test_label_falls_back_when_title_blank(self):
        citation = Citation(title="   ", source="https://example.test/x")
        assert citation.label().startswith("未命名来源")
        assert citation.label().endswith("https://example.test/x")

    def test_label_omits_missing_optional_parts(self):
        citation = Citation(title="通知", source="")
        assert citation.label() == "通知"

    def test_to_dict_round_trip(self):
        citation = Citation(title="t", source="s", snippet="snip", department="d")
        data = citation.to_dict()
        assert data == {
            "title": "t",
            "source": "s",
            "snippet": "snip",
            "published_at": None,
            "department": "d",
            "metadata": {},
        }


class TestStructuredRecordText:
    def test_text_drops_empty_values_and_keeps_zero(self):
        record = StructuredRecord(
            collection="admission_scores",
            data={"province": "湖北", "year": 2024, "min_score": 0, "max_score": None, "note": "", "tags": []},
        )
        # 0 is a real value and must be kept; None / "" / [] are dropped.
        assert record.text() == "admission_scores: province=湖北；year=2024；min_score=0"

    def test_text_with_no_values_is_just_collection(self):
        record = StructuredRecord(collection="empty", data={"a": None, "b": ""})
        assert record.text() == "empty: "

    def test_to_dict_includes_citation_when_present(self):
        record = StructuredRecord(collection="c", data={"x": 1}, citation=Citation(title="t", source="s"), score=2.5)
        assert record.to_dict() == {
            "collection": "c",
            "data": {"x": 1},
            "citation": {"title": "t", "source": "s", "snippet": "", "published_at": None, "department": None, "metadata": {}},
            "score": 2.5,
        }


class TestRetrievedChunk:
    def test_to_dict_without_citation(self):
        chunk = RetrievedChunk(text="hello", score=0.5)
        assert chunk.to_dict() == {"text": "hello", "score": 0.5, "citation": None, "metadata": {}}


class TestRetrievalResult:
    def test_has_evidence_false_when_empty(self):
        assert RetrievalResult().has_evidence is False

    def test_has_evidence_true_with_chunks_or_records(self):
        assert RetrievalResult(chunks=[RetrievedChunk(text="x")]).has_evidence is True
        assert RetrievalResult(structured_records=[StructuredRecord(collection="c", data={})]).has_evidence is True

    def test_citations_dedupes_by_title_and_source(self):
        cite_a = Citation(title="A", source="url-a")
        cite_a_dup = Citation(title="A", source="url-a")  # same (title, source) -> dropped
        cite_b = Citation(title="B", source="url-b")
        # Same title but different source is NOT a duplicate.
        cite_a_other = Citation(title="A", source="url-other")
        result = RetrievalResult(
            structured_records=[StructuredRecord(collection="c", data={}, citation=cite_a)],
            chunks=[
                RetrievedChunk(text="t1", citation=cite_a_dup),
                RetrievedChunk(text="t2", citation=cite_b),
                RetrievedChunk(text="t3", citation=cite_a_other),
                RetrievedChunk(text="t4", citation=None),
            ],
        )
        assert result.citations() == [cite_a, cite_b, cite_a_other]

    def test_citations_preserves_first_seen_order(self):
        result = RetrievalResult(
            chunks=[
                RetrievedChunk(text="t2", citation=Citation(title="B", source="b")),
                RetrievedChunk(text="t1", citation=Citation(title="A", source="a")),
            ]
        )
        assert [c.title for c in result.citations()] == ["B", "A"]


class TestKnowledgeAnswer:
    def test_source_links_text_without_citations(self):
        answer = KnowledgeAnswer(answer="  hi  ", citations=[])
        assert answer.source_links_text() == ""

    def test_source_links_text_renders_source_links(self):
        answer = KnowledgeAnswer(
            answer="回答内容",
            citations=[Citation(title="来源A", source="url-a"), Citation(title="来源B", source="url-b")],
        )
        text = answer.source_links_text()
        assert text.startswith("来源链接：\n")
        assert "url-a（来源A）" in text
        assert "url-b（来源B）" in text

    def test_to_dict_shape(self):
        answer = KnowledgeAnswer(answer="a", citations=[Citation(title="t", source="s")], confidence=0.9, need_follow_up=True)
        data = answer.to_dict()
        assert data["answer"] == "a"
        assert data["confidence"] == 0.9
        assert data["need_follow_up"] is True
        assert data["citations"][0]["title"] == "t"
        assert data["fallback_reason"] is None
