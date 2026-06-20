from __future__ import annotations

import pytest

from luoying_bot.capabilities.knowledge_base.quality import MarkdownQualityChecker


@pytest.fixture()
def checker() -> MarkdownQualityChecker:
    return MarkdownQualityChecker()


CLEAN_DOC = (
    "# 计算机学院本科生培养方案\n\n"
    "本方案适用于计算机科学与技术专业本科生，涵盖课程体系、实践环节与毕业要求。\n"
    "学生需完成必修课程与选修课程，并通过毕业设计答辩方可毕业。\n"
    "详细课程列表与实践学分要求由学院教务办公室每学期更新公布。\n"
)


class TestMarkdownQualityChecker:
    def test_clean_document_passes(self, checker):
        report = checker.check(CLEAN_DOC)
        assert report.ok is True
        assert report.warnings == []
        assert report.score == 1.0
        assert report.metrics["chars"] == len(CLEAN_DOC)
        assert report.metrics["lines"] >= 4

    def test_too_short_document_warned(self, checker):
        report = checker.check("太短了")
        assert report.ok is False
        assert "too_short" in report.warnings

    @pytest.mark.parametrize(
        "noise,name",
        [
            ("首页 学院概况", "main_nav"),
            ("版权所有 武汉大学", "footer"),
            ("您当前位置：首页", "breadcrumb"),
            # script pattern matches `_showDynClick`, `document.`, or `function(` with no name.
            ("_showDynClick(123); document.title='x'", "script"),
        ],
    )
    def test_noise_patterns_detected(self, checker, noise, name):
        report = checker.check(CLEAN_DOC + "\n" + noise)
        assert f"noise:{name}" in report.warnings
        assert report.metrics[f"{name}_hits"] >= 1
        assert report.ok is False

    def test_high_duplicate_line_ratio_warned(self, checker):
        repeated = "\n".join(["同样的内容重复出现"] * 10)
        report = checker.check(repeated)
        assert "high_duplicate_line_ratio" in report.warnings
        assert report.metrics["duplicate_line_ratio"] > 0.2

    def test_score_decreases_with_warning_count(self, checker):
        one = checker.check(CLEAN_DOC + "\n版权所有")
        assert one.score == pytest.approx(1.0 - 0.15 * len(one.warnings))
        assert one.score < 1.0
        assert one.score >= 0.0

    def test_to_dict_round_trip(self, checker):
        report = checker.check(CLEAN_DOC)
        data = report.to_dict()
        assert data["ok"] is True
        assert "score" in data and "metrics" in data
