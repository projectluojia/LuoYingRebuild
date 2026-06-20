from __future__ import annotations

from luoying_bot.capabilities.knowledge_base.postgres_store import dedupe_queries, fuse_ranked_candidates


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


def candidate(
    chunk_id: str,
    *,
    title_score: float = 0.0,
    lexical_score: float = 0.0,
    vector_score: float = 0.0,
) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "document_id": f"doc_{chunk_id}",
        "title": chunk_id,
        "source_url": "https://example.test",
        "published_at": None,
        "text": chunk_id,
        "embedding_model": "test",
        "title_score": title_score,
        "lexical_score": lexical_score,
        "vector_score": vector_score,
    }
