"""
Lightweight emotion detection for Luoying's TTS + Live2D expressions.

Uses keyword + punctuation heuristics instead of an extra LLM call.
The default mood is "gentle" to match 珞樱's base personality.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# Emotion keywords with weights — higher weight = stronger signal
EMOTION_LEXICON: dict[str, list[tuple[str, float]]] = {
    "happy": [
        ("哈哈", 3.0), ("嘻嘻", 2.5), ("真不错", 2.0), ("太好了", 2.5),
        ("开心", 2.0), ("喜欢", 1.5), ("耶", 2.0), ("棒", 1.5),
        ("太好了", 3.0), ("恭喜", 2.0), ("赞", 1.5), ("快乐", 2.0),
        ("高兴", 2.0), ("好玩", 1.5), ("有趣", 1.5), ("爱你", 2.0),
    ],
    "sad": [
        ("对不起", 2.5), ("抱歉", 2.0), ("难过", 2.5), ("遗憾", 2.0),
        ("可惜", 2.0), ("不要太难过", 1.5), ("节哀", 3.0), ("哭", 1.5),
        ("伤心", 2.5), ("心疼", 2.0), ("辛苦了", 1.0), ("没事的", 1.5),
        ("抱抱", 1.5),
    ],
    "angry": [
        ("过分", 2.5), ("混蛋", 3.0), ("无耻", 3.0), ("可恶", 2.0),
        ("垃圾", 2.5), ("警告", 2.0), ("坚决反对", 2.5), ("不可容忍", 3.0),
        ("恶劣", 2.0), ("严正", 2.0),
    ],
    "surprise": [
        ("居然", 2.0), ("什么", 1.0), ("哇", 2.0), ("真的假的", 2.5),
        ("天哪", 2.5), ("没想到", 2.0), ("怎么可能", 2.5), ("太神奇", 2.5),
        ("震惊", 3.0), ("不可思议", 2.5),
    ],
    "gentle": [
        ("晚安", 1.5), ("好梦", 1.5), ("没事", 1.0), ("慢慢来", 1.5),
        ("加油", 1.0), ("相信你", 1.5), ("陪你", 1.5), ("乖", 1.5),
        ("可爱", 1.0), ("温柔", 1.0), ("照顾", 1.5), ("放心", 1.0),
    ],
}

# Emoji → emotion
EMOJI_EMOTION: dict[str, str] = {
    "😊": "happy", "😄": "happy", "😆": "happy", "🥰": "happy",
    "😢": "sad", "😭": "sad", "🥺": "sad",
    "😤": "angry", "😡": "angry",
    "😲": "surprise", "😮": "surprise", "😯": "surprise",
    "🌸": "gentle", "💕": "gentle",
}


@dataclass
class EmotionResult:
    primary: str       # "happy" | "sad" | "angry" | "surprise" | "gentle" | "neutral"
    confidence: float  # 0.0 ~ 1.0
    mixed: list[str]   # secondary emotions present
    reasoning: str     # short debug note


def detect_emotion(text: str) -> EmotionResult:
    """Detect the primary emotion for a sentence of Luoying's reply.

    The result drives TTS emotional voice style and Live2D expression.
    """
    if not text or not text.strip():
        return EmotionResult(primary="gentle", confidence=0.5, mixed=[], reasoning="empty text")

    scores: dict[str, float] = {k: 0.0 for k in EMOTION_LEXICON}

    # Keyword scoring
    for emotion, keywords in EMOTION_LEXICON.items():
        for keyword, weight in keywords:
            count = text.count(keyword)
            if count > 0:
                scores[emotion] += weight * count

    # Emoji scoring
    for emoji_char, emotion in EMOJI_EMOTION.items():
        if emoji_char in text:
            scores[emotion] += 1.5

    # Punctuation heuristics
    if text.endswith("!") or "！！" in text:
        if any(kw in text for kw in ["开心", "太好了", "恭喜", "耶", "哈哈"]):
            scores["happy"] += 2.0
        elif any(kw in text for kw in ["过分", "混蛋", "垃圾", "警告"]):
            scores["angry"] += 2.0
        else:
            scores["surprise"] += 1.0

    if text.endswith("~") or text.endswith("～"):
        scores["gentle"] += 1.0

    if "..." in text:
        scores["sad"] += 0.5

    # Find primary emotion
    high_scorers = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    primary_emotion, top_score = high_scorers[0]
    secondary = [e for e, s in high_scorers[1:] if s > 0.5]

    # If no strong signal, default to gentle (珞樱's base personality)
    if top_score < 1.0:
        return EmotionResult(
            primary="gentle",
            confidence=0.4,
            mixed=secondary,
            reasoning="weak signal, default gentle",
        )

    # Normalize confidence (cap at 1.0)
    confidence = min(top_score / 5.0, 1.0)

    # Build reasoning note
    top_keywords = []
    for kw, w in EMOTION_LEXICON.get(primary_emotion, []):
        if kw in text:
            top_keywords.append(kw)
    reasoning = f"matched: {', '.join(top_keywords[:3])}" if top_keywords else "emoji/punctuation"

    return EmotionResult(
        primary=primary_emotion,
        confidence=confidence,
        mixed=secondary,
        reasoning=reasoning,
    )


def split_sentences(text: str) -> list[str]:
    """Split a paragraph into speakable sentences for TTS.

    Handles Chinese punctuation: 。！？，；： and newlines.
    Also splits very long sentences (> ~60 chars) at commas for natural pacing.
    """
    # Pre-split on strong breaks
    parts = re.split(r"(?<=[。！？\n])", text)
    result: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Split long clauses on commas for breath pacing
        if len(part) > 60:
            sub_parts = re.split(r"(?<=[，；：,])", part)
            result.extend(p.strip() for p in sub_parts if p.strip())
        else:
            result.append(part)
    return result


def annotate_sentences(sentences: list[str]) -> list[tuple[str, str]]:
    """Split text into sentences and annotate each with emotion.

    Returns list of (text, emotion) tuples ready for TTS synthesis.
    """
    annotated: list[tuple[str, str]] = []
    for sent in sentences:
        emotion = detect_emotion(sent).primary
        annotated.append((sent, emotion))
    return annotated
