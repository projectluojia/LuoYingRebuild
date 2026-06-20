"""Shared, dependency-free text helpers for the knowledge-base capability.

These small pure functions used to be duplicated across several modules
(``normalize_entity_text`` / ``normalize_text`` / ``compact_text``, ``optional_text``,
``longest_common_substring_length``, ``sha256_text``, ``now_iso``). They live here once so
behavior cannot drift between copies.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

_CJK_ALNUM_RE = re.compile(r"[一-鿿A-Za-z0-9]+")


def normalize_alnum_text(value: Any) -> str:
    """Lowercase and keep only CJK and ASCII alphanumeric characters."""
    return "".join(_CJK_ALNUM_RE.findall(str(value).lower()))


def optional_text(value: Any) -> str | None:
    """Return the stripped text, or ``None`` when empty/falsy."""
    text = str(value or "").strip()
    return text or None


def longest_common_substring_length(left: str, right: str) -> int:
    best = 0
    previous = [0] * (len(right) + 1)
    for left_char in left:
        current = [0] * (len(right) + 1)
        for index, right_char in enumerate(right, start=1):
            if left_char != right_char:
                continue
            current[index] = previous[index - 1] + 1
            best = max(best, current[index])
        previous = current
    return best


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
