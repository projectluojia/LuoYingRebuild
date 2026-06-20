from __future__ import annotations

import re
from dataclasses import dataclass, field


NOISE_PATTERNS = {
    "main_nav": re.compile(r"首页\s+学院概况"),
    "footer": re.compile(r"版权所有|邮编：|微信公众号"),
    "breadcrumb": re.compile(r"您当前位置|当前位置："),
    "script": re.compile(r"_showDynClick|function\s*\(|document\."),
    "pagination": re.compile(r"首页\s*\n\s*上页\s*\n\s*\d+\s*\n\s*下页\s*\n\s*尾页"),
}


@dataclass(slots=True)
class QualityReport:
    ok: bool
    score: float
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, int | float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "score": self.score,
            "warnings": self.warnings,
            "metrics": self.metrics,
        }


class MarkdownQualityChecker:
    def check(self, markdown: str) -> QualityReport:
        warnings: list[str] = []
        metrics: dict[str, int | float] = {
            "chars": len(markdown),
            "lines": len(markdown.splitlines()),
        }
        if len(markdown.strip()) < 80:
            warnings.append("too_short")
        for name, pattern in NOISE_PATTERNS.items():
            count = len(pattern.findall(markdown))
            metrics[f"{name}_hits"] = count
            if count:
                warnings.append(f"noise:{name}")
        duplicate_ratio = self._duplicate_line_ratio(markdown)
        metrics["duplicate_line_ratio"] = round(duplicate_ratio, 4)
        if duplicate_ratio > 0.2:
            warnings.append("high_duplicate_line_ratio")
        score = max(0.0, 1.0 - 0.15 * len(warnings))
        return QualityReport(ok=not warnings, score=round(score, 3), warnings=warnings, metrics=metrics)

    def _duplicate_line_ratio(self, markdown: str) -> float:
        lines = [line.strip() for line in markdown.splitlines() if line.strip()]
        if not lines:
            return 0.0
        return (len(lines) - len(set(lines))) / len(lines)
