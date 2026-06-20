from __future__ import annotations

import pytest

from luoying_bot.capabilities.knowledge_base.analytics import (
    KnowledgeAnalyticsEngine,
    extract_year,
    validate_select_sql,
)
from luoying_bot.capabilities.knowledge_base.entities import EntityMatch
from luoying_bot.capabilities.knowledge_base.entity_resolver import EntityResolution
from luoying_bot.capabilities.knowledge_base.models import KnowledgeQuery
from luoying_bot.capabilities.knowledge_base.semantic_layer import KnowledgeSemanticLayer

from _fakes import FakeAnalyticsBackend, FakeChatModel, FakeStructuredBackend


def _engine() -> KnowledgeAnalyticsEngine:
    return KnowledgeAnalyticsEngine(
        backend=FakeAnalyticsBackend(),
        value_backend=FakeStructuredBackend(),
        model=FakeChatModel(),
        semantic_layer=KnowledgeSemanticLayer(),
        max_rows=50,
    )


def _fact_entity(*, score: float, alias_type: str = "search_item") -> EntityMatch:
    return EntityMatch(
        entity_id="prog_1",
        space_id="whu",
        entity_type="program",
        canonical_name="数学与应用数学（智能科学）强基计划",
        metadata={
            "fact_table": "admission_strong_foundation_scores",
            "fact_column": "program_name",
        },
        matched_alias="强基",
        alias_type=alias_type,
        score=score,
        confidence=0.9,
    )


class TestEntityPlanConfidenceGate:
    """Regression: _entity_plan must ignore low-confidence entity matches.

    A noisy match (e.g. a 强基 program pulled into a non-强基 question at score ~6) used
    to drive the SQL against the wrong fact table, return 0 rows, and silently shadow the
    LLM planner. Only score>=100 or relation_resolution entities may drive the plan.
    """

    def test_low_confidence_fact_entity_is_skipped(self):
        engine = _engine()
        query = KnowledgeQuery(question="武汉大学2024年在湖北的录取分数线是多少？", space_id="whu", top_k=8)
        entities = EntityResolution(matches=(_fact_entity(score=6.4),))
        # score 6.4, not relation_resolution -> must NOT drive the plan
        assert engine._entity_plan(query, entities) is None

    def test_relation_resolution_entity_drives_plan(self):
        engine = _engine()
        query = KnowledgeQuery(question="2025年强基计划在湖北的最低分是多少？", space_id="whu", top_k=8)
        entities = EntityResolution(matches=(_fact_entity(score=140.0, alias_type="relation_resolution"),))
        plan = engine._entity_plan(query, entities)
        assert plan is not None
        assert "admission_strong_foundation_scores" in plan.sql
        assert "program_name = " in plan.sql
        assert "year = 2025" in plan.sql

    def test_high_score_entity_drives_plan(self):
        engine = _engine()
        query = KnowledgeQuery(question="2025年强基计划在湖北的最低分是多少？", space_id="whu", top_k=8)
        entities = EntityResolution(matches=(_fact_entity(score=110.0),))
        plan = engine._entity_plan(query, entities)
        assert plan is not None
        assert "admission_strong_foundation_scores" in plan.sql


class TestValidateSelectSql:
    ALLOWED = {"admission_scores", "admission_plans"}

    def test_valid_select_wraps_missing_limit(self):
        safe = validate_select_sql(
            "select * from admission_scores where review_status = 'approved'",
            allowed_tables=self.ALLOWED,
            max_rows=50,
        )
        assert "kb_analytics_result limit 50" in safe

    def test_non_select_rejected(self):
        with pytest.raises(ValueError):
            validate_select_sql("delete from admission_scores", allowed_tables=self.ALLOWED, max_rows=50)

    def test_disallowed_table_rejected(self):
        with pytest.raises(ValueError):
            validate_select_sql("select * from users", allowed_tables=self.ALLOWED, max_rows=50)

    def test_semicolon_rejected(self):
        with pytest.raises(ValueError):
            validate_select_sql(
                "select * from admission_scores; drop table admission_scores",
                allowed_tables=self.ALLOWED,
                max_rows=50,
            )

    def test_oversize_limit_clamped(self):
        safe = validate_select_sql(
            "select * from admission_scores limit 999",
            allowed_tables=self.ALLOWED,
            max_rows=50,
        )
        assert safe.endswith("limit 50")


class TestExtractYear:
    @pytest.mark.parametrize(
        "question,expected",
        [
            ("2024年在湖北的分数线", 2024),
            ("2025年招生计划", 2025),
            ("24年的数据", 2024),
            ("85年", 1985),
            ("今年", None),
        ],
    )
    def test_extract(self, question, expected):
        assert extract_year(question) == expected
