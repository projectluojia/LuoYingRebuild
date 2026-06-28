from __future__ import annotations

import pytest

from luoying_bot.capabilities.knowledge_base.errors import BackendUnavailable
from luoying_bot.capabilities.knowledge_base.rerankers import LlmReranker, RerankCandidate, parse_rerank_response

from _fakes import FakeChatModel


class SequenceChatModel(FakeChatModel):
    def __init__(self, responses: list[str]):
        super().__init__(responses[0])
        self.responses = responses

    async def chat(self, messages: list[dict[str, str]], temperature: float | None = None) -> str:
        self.calls.append((messages, temperature))
        return self.responses[len(self.calls) - 1]


@pytest.mark.asyncio
async def test_llm_reranker_orders_by_model_score_then_initial_score():
    model = FakeChatModel(
        '{"results":['
        '{"id":"a","score":80,"rationale":"相关"},'
        '{"id":"b","score":95,"rationale":"直接回答"},'
        '{"id":"c","score":80,"rationale":"同分"}'
        ']}'
    )
    reranker = LlmReranker(model, candidate_limit=3, max_text_chars=40)

    ranked = await reranker.rerank(
        question="问题",
        candidates=[
            RerankCandidate(candidate_id="a", title="A", source="u", text="text", initial_score=0.2),
            RerankCandidate(candidate_id="b", title="B", source="u", text="text", initial_score=0.1),
            RerankCandidate(candidate_id="c", title="C", source="u", text="text", initial_score=0.3),
        ],
        top_k=3,
    )

    assert [item.candidate.candidate_id for item in ranked] == ["b", "c", "a"]
    assert ranked[0].score == 95
    assert ranked[0].rationale == "直接回答"
    assert model.calls[0][1] == 0.0


def test_parse_rerank_response_requires_every_candidate():
    with pytest.raises(BackendUnavailable, match="omitted candidate ids"):
        parse_rerank_response(
            '{"results":[{"id":"a","score":100,"rationale":"命中"}]}',
            expected_ids=["a", "b"],
        )


@pytest.mark.asyncio
async def test_llm_reranker_scores_candidates_in_strict_batches():
    model = SequenceChatModel(
        [
            '{"results":[{"id":"a","score":20,"rationale":"弱相关"},{"id":"b","score":90,"rationale":"命中"}]}',
            '{"results":[{"id":"c","score":80,"rationale":"相关"}]}',
        ]
    )
    reranker = LlmReranker(model, candidate_limit=3, batch_size=2, max_text_chars=40)

    ranked = await reranker.rerank(
        question="问题",
        candidates=[
            RerankCandidate(candidate_id="a", title="A", source="u", text="text"),
            RerankCandidate(candidate_id="b", title="B", source="u", text="text"),
            RerankCandidate(candidate_id="c", title="C", source="u", text="text"),
        ],
        top_k=3,
    )

    assert [item.candidate.candidate_id for item in ranked] == ["b", "c", "a"]
    assert len(model.calls) == 2
