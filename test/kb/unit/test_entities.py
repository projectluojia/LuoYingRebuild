from __future__ import annotations

import pytest

from luoying_bot.capabilities.knowledge_base.entities import (
    EntityMatch,
    entity_match_score,
    longest_common_substring_length,
    normalize_entity_text,
    parse_metadata,
    stable_entity_id,
    stable_search_item_id,
)


class TestNormalizeEntityText:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("武汉大学", "武汉大学"),
            ("武 汉 大 学", "武汉大学"),  # spaces dropped
            ("AI 人工智能！", "ai人工智能"),  # lowercased ascii, punctuation dropped
            ("", ""),
            ("  ", ""),
        ],
    )
    def test_normalization(self, raw, expected):
        assert normalize_entity_text(raw) == expected


class TestStableIds:
    def test_entity_id_is_deterministic(self):
        a = stable_entity_id("sai", "school", "武汉大学")
        b = stable_entity_id("sai", "school", "武汉大学")
        assert a == b

    def test_entity_id_keys_on_normalized_name(self):
        # Whitespace and case must not change the id.
        spaced = stable_entity_id("sai", "school", "武 汉 大学")
        plain = stable_entity_id("sai", "school", "武汉大学")
        assert spaced == plain

    def test_entity_id_format(self):
        value = stable_entity_id("sai", "school", "武汉大学")
        assert value.startswith("sai_school_")
        digest = value.split("school_", 1)[1]
        assert len(digest) == 16
        int(digest, 16)  # hex digest

    def test_entity_id_differs_by_type_or_space(self):
        assert stable_entity_id("sai", "school", "X") != stable_entity_id("sai", "major", "X")
        assert stable_entity_id("sai", "school", "X") != stable_entity_id("whu", "school", "X")

    def test_search_item_id_format(self):
        value = stable_search_item_id("sai", "entity", "https://example.test/a")
        assert value.startswith("sai_entity_")
        assert len(value.split("entity_", 1)[1]) == 20


class TestParseMetadata:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ({"a": 1}, {"a": 1}),  # dict passthrough
            ('{"a": 2}', {"a": 2}),  # valid json string
            ("not json", {}),  # invalid json string
            ("[1, 2, 3]", {}),  # json but not a dict
            ("", {}),  # empty string
            (None, {}),  # None
            ("   ", {}),  # whitespace only
        ],
    )
    def test_parse(self, raw, expected):
        assert parse_metadata(raw) == expected


class TestLongestCommonSubstring:
    @pytest.mark.parametrize(
        "left,right,expected",
        [
            ("abc", "abc", 3),
            ("abcde", "abfcd", 2),  # "ab" or "cd"
            ("xyz", "abc", 0),
            ("", "abc", 0),
            ("武汉大学", "武汉信息", 2),  # "武汉"
        ],
    )
    def test_lcs(self, left, right, expected):
        assert longest_common_substring_length(left, right) == expected


class TestEntityMatchScore:
    def test_alias_substring_in_query_scores_highest(self):
        score = entity_match_score(query_norm="武汉大学计算机学院", alias_norm="计算机学院", canonical_norm="计算机")
        assert score == 100.0 + len("计算机学院")

    def test_alias_score_capped_at_30_length_bonus(self):
        long_alias = "a" * 50
        score = entity_match_score(query_norm=long_alias, alias_norm=long_alias, canonical_norm="x")
        assert score == 130.0  # 100 + min(50, 30)

    def test_canonical_substring_when_alias_absent(self):
        score = entity_match_score(query_norm="xyz计算机学院", alias_norm="cs", canonical_norm="计算机学院")
        assert score == 92.0 + len("计算机学院")

    def test_empty_inputs_score_zero(self):
        assert entity_match_score(query_norm="", alias_norm="x", canonical_norm="y") == 0.0
        assert entity_match_score(query_norm="x", alias_norm="", canonical_norm="y") == 0.0

    def test_overlap_below_threshold_is_zero(self):
        # alias len 2 -> threshold 2; overlap 1 < 2 -> 0
        assert entity_match_score(query_norm="ab", alias_norm="ac", canonical_norm="") == 0.0

    def test_overlap_above_threshold_is_partial(self):
        # alias "abcd" (len 4 -> threshold 3); query contains "abc" (overlap 3); coverage 3/4
        score = entity_match_score(query_norm="zzabczz", alias_norm="abcd", canonical_norm="")
        assert score == pytest.approx(35.0 + 40.0 * (3 / 4))


class TestEntityMatchFromRow:
    def test_from_row_with_metadata_json_string(self):
        row = {
            "entity_id": "e1",
            "space_id": "sai",
            "entity_type": "school",
            "canonical_name": "武汉大学",
            "description": "desc",
            "metadata_json": '{"fact_table": "admission_scores"}',
            "matched_alias": "武大",
            "alias_type": "alias",
            "score": 110.0,
            "confidence": 0.9,
        }
        match = EntityMatch.from_row(row)
        assert match.entity_id == "e1"
        assert match.metadata == {"fact_table": "admission_scores"}
        assert match.score == 110.0
        assert match.confidence == 0.9

    def test_from_row_falls_back_to_metadata_dict_and_defaults(self):
        match = EntityMatch.from_row(
            {"entity_id": "e2", "space_id": "sai", "entity_type": "major", "canonical_name": "AI", "metadata": {}}
        )
        assert match.description == ""
        assert match.score == 0.0
        assert match.confidence == 0.0

    def test_prompt_line_includes_type_name_and_confidence(self):
        match = EntityMatch(
            entity_id="e3",
            space_id="sai",
            entity_type="school",
            canonical_name="武汉大学",
            confidence=0.5,
            metadata={"province": "湖北", "empty": ""},
        )
        line = match.prompt_line()
        assert "type=school" in line
        assert "name=武汉大学" in line
        assert "confidence=0.50" in line
        assert "province=湖北" in line
        assert "empty=" not in line  # empty metadata values are dropped
