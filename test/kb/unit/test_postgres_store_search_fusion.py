from __future__ import annotations

from luoying_bot.capabilities.knowledge_base.postgres_store import (
    combine_page_contexts,
    dedupe_queries,
    diversify_candidates_for_rerank,
    fuse_ranked_candidates,
    group_reranks_by_content,
    parade_query_text,
)
from luoying_bot.capabilities.knowledge_base.rerankers import RerankCandidate, RerankedCandidate


def test_dedupe_queries_keeps_distinct_routes():
    assert dedupe_queries([" 保研要求 ", "保研要求", "推免实施细则"]) == ["保研要求", "推免实施细则"]


def test_rrf_fusion_promotes_result_found_by_expanded_route():
    original_vector = [
        candidate("noise_1", vector_score=0.72),
        candidate("noise_2", vector_score=0.71),
        candidate("target", vector_score=0.68),
    ]
    expanded_title = [
        candidate("target", title_score=3.8),
        candidate("noise_3", title_score=2.0),
    ]

    fused = fuse_ranked_candidates(
        [
            ("route_1:vector", 1.0, original_vector),
            ("route_2:title", 1.35, expanded_title),
        ]
    )
    ranked = sorted(
        fused,
        key=lambda item: (float(item["score"]), float(item["best_raw_score"])),
        reverse=True,
    )

    assert ranked[0]["chunk_id"] == "target"
    assert {match["source"] for match in ranked[0]["retrieval_matches"]} == {
        "route_1:vector",
        "route_2:title",
    }
    assert all("weight" in match for match in ranked[0]["retrieval_matches"])


def test_rrf_fusion_merges_entity_and_bm25_scores():
    entity_candidates = [
        {
            **candidate("target", entity_score=11.0),
            "matched_entities": [{"entity_id": "e_leijun", "canonical_name": "雷军班"}],
        }
    ]
    bm25_candidates = [
        candidate("target", bm25_score=9.0),
        candidate("noise", bm25_score=8.5),
    ]

    fused = fuse_ranked_candidates(
        [
            ("entity", 1.45, entity_candidates),
            ("route_1:bm25", 1.25, bm25_candidates),
        ]
    )
    target = next(item for item in fused if item["chunk_id"] == "target")

    assert target["entity_score"] == 11.0
    assert target["bm25_score"] == 9.0
    assert target["matched_entities"] == [{"entity_id": "e_leijun", "canonical_name": "雷军班"}]
    assert {match["source"] for match in target["retrieval_matches"]} == {"entity", "route_1:bm25"}


def test_parade_query_text_preserves_chinese_keywords():
    assert parade_query_text("  雷军班\n强基  分省计划表在哪里  ") == "雷军班 强基 分省计划表在哪里"


def test_group_reranks_by_content_combines_same_page_hits():
    reranked = [
        reranked_candidate("doc_a:1", 96),
        reranked_candidate("doc_a:2", 92),
        reranked_candidate("doc_b:0", 90),
        reranked_candidate("doc_c:0", 88),
    ]
    by_chunk_id = {
        "doc_a:1": candidate("doc_a:1", document_id="doc_a"),
        "doc_a:2": candidate("doc_a:2", document_id="doc_a"),
        "doc_b:0": candidate("doc_b:0", document_id="doc_b"),
        "doc_c:0": candidate("doc_c:0", document_id="doc_c"),
    }

    groups = group_reranks_by_content(reranked, by_chunk_id, top_k=2)

    assert [[item.candidate.candidate_id for item in group] for group in groups] == [
        ["doc_a:1", "doc_a:2"],
        ["doc_b:0"],
    ]


def test_group_reranks_by_content_deduplicates_mirrored_documents():
    reranked = [
        reranked_candidate("mirror_a:0", 96),
        reranked_candidate("mirror_b:0", 94),
        reranked_candidate("target:0", 90),
        reranked_candidate("other:0", 88),
    ]
    by_chunk_id = {
        "mirror_a:0": candidate("mirror_a:0", document_id="mirror_a", content_hash="same_content"),
        "mirror_b:0": candidate("mirror_b:0", document_id="mirror_b", content_hash="same_content"),
        "target:0": candidate("target:0", document_id="target", content_hash="target_content"),
        "other:0": candidate("other:0", document_id="other", content_hash="other_content"),
    }

    groups = group_reranks_by_content(reranked, by_chunk_id, top_k=2)

    assert [[item.candidate.candidate_id for item in group] for group in groups] == [
        ["mirror_a:0", "mirror_b:0"],
        ["target:0"],
    ]


def test_diversify_candidates_for_rerank_prevents_one_page_from_filling_pool():
    candidates = [
        candidate(f"news:{index}", content_hash="same_news")
        for index in range(5)
    ]
    candidates.append(candidate("training_plan:2", content_hash="training_plan"))

    diversified = diversify_candidates_for_rerank(candidates, per_content_limit=2)

    assert [item["chunk_id"] for item in diversified[:3]] == [
        "news:0",
        "news:1",
        "training_plan:2",
    ]


def test_combine_page_contexts_deduplicates_identical_expansions():
    assert combine_page_contexts(["师资力量", " 师资力量 ", "专业培养计划"]) == (
        "【同页命中 1】\n师资力量\n\n【同页命中 2】\n专业培养计划"
    )


def candidate(
    chunk_id: str,
    *,
    document_id: str | None = None,
    content_hash: str | None = None,
    title_score: float = 0.0,
    entity_score: float = 0.0,
    bm25_score: float = 0.0,
    vector_score: float = 0.0,
) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "document_id": document_id or f"doc_{chunk_id}",
        "content_hash": content_hash or f"hash_{document_id or chunk_id}",
        "title": chunk_id,
        "source_url": "https://example.test",
        "published_at": None,
        "text": chunk_id,
        "embedding_model": "test",
        "title_score": title_score,
        "entity_score": entity_score,
        "bm25_score": bm25_score,
        "vector_score": vector_score,
    }


def reranked_candidate(chunk_id: str, score: float) -> RerankedCandidate:
    return RerankedCandidate(
        candidate=RerankCandidate(
            candidate_id=chunk_id,
            title=chunk_id,
            text=chunk_id,
            source="https://example.test",
        ),
        score=score,
    )
