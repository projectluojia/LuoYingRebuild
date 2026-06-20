from __future__ import annotations

import pytest

from luoying_bot.capabilities.knowledge_base.semantic_layer import KnowledgeSemanticLayer


@pytest.fixture(scope="module")
def layer() -> KnowledgeSemanticLayer:
    return KnowledgeSemanticLayer()


EXPECTED_TABLES = {
    "admission_scores",
    "admission_plans",
    "admission_strong_foundation_scores",
    "majors",
    "class_types",
    "admission_articles",
    "academic_units",
    "admission_schools",
    "admission_media_items",
}


class TestTableSchema:
    def test_allowed_tables_matches_expected(self, layer):
        assert layer.allowed_tables == EXPECTED_TABLES

    def test_table_columns_known(self, layer):
        cols = layer.table_columns("admission_scores")
        assert "min_score" in cols
        assert "province" in cols
        assert "review_status" in cols

    def test_table_columns_unknown_is_empty(self, layer):
        assert layer.table_columns("does_not_exist") == ()

    def test_filter_fields_by_table_is_complete_and_sets(self, layer):
        fields = layer.filter_fields_by_table()
        assert set(fields) == EXPECTED_TABLES
        assert isinstance(fields["admission_scores"], set)
        # every table must expose at least the review_status column used by the rules
        for table, cols in fields.items():
            assert "review_status" in cols, table


class TestValueHintFields:
    def test_all_hint_fields_are_real_columns(self, layer):
        fields = layer.value_hint_fields()
        assert fields, "value_hint_fields should not be empty"
        for table, field in fields:
            assert table in layer.allowed_tables
            assert field in layer.table_columns(table)

    def test_hint_includes_province_and_major(self, layer):
        pairs = set(layer.value_hint_fields())
        assert ("admission_scores", "province") in pairs
        assert ("majors", "name") in pairs


class TestIsAnalyticsQuestion:
    @pytest.mark.parametrize(
        "question",
        [
            "武汉大学在湖北的分数线是多少？",
            "计算机专业招生计划多少人？",
            "强基计划录取最低分",
            "有哪些学院？",
            "试验班有哪些？",
        ],
    )
    def test_positive_cases(self, layer, question):
        assert layer.is_analytics_question(question) is True

    @pytest.mark.parametrize("question", ["你好", "谢谢老师", "今天几号"])
    def test_negative_cases(self, layer, question):
        assert layer.is_analytics_question(question) is False


class TestPromptContext:
    def test_prompt_context_lists_every_table(self, layer):
        context = layer.prompt_context()
        for table in EXPECTED_TABLES:
            assert f"Table: {table}" in context
        assert "Description:" in context
        assert "Columns:" in context

    def test_semantic_rules_non_empty_and_mentions_review_status(self, layer):
        rules = layer.semantic_rules()
        assert rules.strip()
        assert "review_status" in rules
