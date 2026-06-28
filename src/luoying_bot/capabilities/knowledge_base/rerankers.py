from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from luoying_bot.capabilities.knowledge_base.errors import BackendUnavailable
from luoying_bot.ports.llm import ChatModel


@dataclass(frozen=True, slots=True)
class RerankCandidate:
    candidate_id: str
    title: str
    text: str
    source: str
    initial_score: float = 0.0


@dataclass(frozen=True, slots=True)
class RerankedCandidate:
    candidate: RerankCandidate
    score: float
    rationale: str = ""


class Reranker(Protocol):
    async def rerank(
        self,
        *,
        question: str,
        candidates: list[RerankCandidate],
        top_k: int,
    ) -> list[RerankedCandidate]: ...


class LlmReranker:
    def __init__(
        self,
        model: ChatModel,
        *,
        candidate_limit: int = 40,
        batch_size: int = 20,
        max_text_chars: int = 900,
    ):
        if candidate_limit <= 0:
            raise ValueError("candidate_limit must be positive")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if max_text_chars <= 0:
            raise ValueError("max_text_chars must be positive")
        self.model = model
        self.candidate_limit = candidate_limit
        self.batch_size = batch_size
        self.max_text_chars = max_text_chars

    async def rerank(
        self,
        *,
        question: str,
        candidates: list[RerankCandidate],
        top_k: int,
    ) -> list[RerankedCandidate]:
        if not candidates:
            return []
        selected = candidates[: self.candidate_limit]
        scores: dict[str, tuple[float, str]] = {}
        for batch in candidate_batches(selected, self.batch_size):
            scores.update(await self._score_batch(question=question, candidates=batch))
        ranked = [
            RerankedCandidate(
                candidate=candidate,
                score=scores[candidate.candidate_id][0],
                rationale=scores[candidate.candidate_id][1],
            )
            for candidate in selected
        ]
        ranked.sort(key=lambda item: (item.score, item.candidate.initial_score), reverse=True)
        return ranked[:top_k]

    async def _score_batch(
        self,
        *,
        question: str,
        candidates: list[RerankCandidate],
    ) -> dict[str, tuple[float, str]]:
        payload = [
            {
                "id": candidate.candidate_id,
                "title": candidate.title,
                "source": candidate.source,
                "text": truncate_text(candidate.text, self.max_text_chars),
            }
            for candidate in candidates
        ]
        raw = await self.model.chat(
            [
                {"role": "system", "content": RERANK_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": RERANK_USER_PROMPT.format(
                        question=question.strip(),
                        candidates=json.dumps(payload, ensure_ascii=False),
                    ),
                },
            ],
            temperature=0.0,
        )
        return parse_rerank_response(raw, expected_ids=[candidate.candidate_id for candidate in candidates])


RERANK_SYSTEM_PROMPT = """\
你是知识库检索重排器。你只判断候选材料是否能直接回答用户问题，不生成答案。
必须输出严格 JSON，不要输出 Markdown、解释或多余文本。
"""


RERANK_USER_PROMPT = """\
请按用户问题对候选材料逐项打分。

评分规则：
- 100：材料直接回答问题，且包含关键限定条件。
- 70-90：高度相关，但需要结合少量上下文。
- 40-69：主题相关，但不能直接回答。
- 1-39：弱相关。
- 0：无关、过时、范围错误或只是同名噪声。

排序原则：
- 对总览、目录、名单、有哪些、在哪里等泛问，优先能覆盖整个问题范围的官方总览页、目录页、列表页。
- 子类别、单条新闻、单个通知、单个活动材料即使相关，也应低于覆盖范围更完整的材料。
- 只有最直接、范围最匹配的候选才给 95-100；不要给一批候选相同满分，除非它们内容等价。
- 如果标题或结构入口显示材料是目录/栏目页，且正文提供对应列表，应高于只在正文中顺带提到关键词的材料。

硬性要求：
- 必须为每一个候选 id 返回一条结果。
- score 必须是 0 到 100 的数字。
- rationale 用 20 字以内中文短语说明。
- 只输出 JSON：{{"results":[{{"id":"...","score":0,"rationale":"..."}}]}}

用户问题：
{question}

候选材料 JSON：
{candidates}
"""


def parse_rerank_response(raw: str, *, expected_ids: list[str]) -> dict[str, tuple[float, str]]:
    data = parse_json_object(raw)
    rows = data.get("results")
    if not isinstance(rows, list):
        raise BackendUnavailable("reranker response missing results array")
    expected = set(expected_ids)
    scores: dict[str, tuple[float, str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise BackendUnavailable("reranker response contains non-object result")
        candidate_id = str(row.get("id") or "").strip()
        if candidate_id not in expected:
            raise BackendUnavailable(f"reranker returned unknown candidate id: {candidate_id}")
        score_value = row.get("score")
        if score_value is None:
            raise BackendUnavailable(f"reranker returned missing score for {candidate_id}")
        try:
            score = float(score_value)
        except (TypeError, ValueError) as exc:
            raise BackendUnavailable(f"reranker returned invalid score for {candidate_id}") from exc
        if not 0.0 <= score <= 100.0:
            raise BackendUnavailable(f"reranker score out of range for {candidate_id}: {score}")
        scores[candidate_id] = (score, str(row.get("rationale") or "").strip())
    missing = expected - set(scores)
    if missing:
        raise BackendUnavailable(f"reranker omitted candidate ids: {', '.join(sorted(missing)[:5])}")
    return scores


def parse_json_object(raw: str) -> dict[str, object]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise BackendUnavailable("reranker response is not JSON")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise BackendUnavailable("reranker response is not valid JSON") from exc
    if not isinstance(data, dict):
        raise BackendUnavailable("reranker response must be a JSON object")
    return data


def candidate_batches(candidates: list[RerankCandidate], batch_size: int) -> list[list[RerankCandidate]]:
    return [candidates[index : index + batch_size] for index in range(0, len(candidates), batch_size)]


def truncate_text(text: str, max_chars: int) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= max_chars:
        return clean
    return f"{clean[:max_chars].rstrip()}..."
