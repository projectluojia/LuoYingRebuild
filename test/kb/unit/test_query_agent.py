from __future__ import annotations

import pytest

from luoying_bot.capabilities.knowledge_base.entity_resolver import EntityResolver
from luoying_bot.capabilities.knowledge_base.models import KnowledgeQuery
from luoying_bot.capabilities.knowledge_base.query_agent import (
    KBQueryAgent,
    rag_query_routes,
)
from luoying_bot.capabilities.knowledge_base.entities import GLOBAL_ENTITY_SPACE_ID, EntityMatch

from _fakes import FakeEntityBackend, FakeRagBackend


class FakeAnalyticsEngine:
    async def query(self, query, entities):
        return []


@pytest.mark.asyncio
async def test_resolved_entity_aliases_add_expanded_rag_route():
    entity_backend = FakeEntityBackend(
        items=[
            {
                "entity_id": "e_sai",
                "space_id": GLOBAL_ENTITY_SPACE_ID,
                "title": "人工智能学院",
                "metadata_json": {
                    "entity_type": "school",
                    "canonical_name": "人工智能学院",
                    "aliases": ["人工智能学院", "武汉大学人工智能学院"],
                    "entity_metadata": {},
                },
                "score": 0.0,
            },
            {
                "entity_id": "e_recommended_exemption",
                "space_id": GLOBAL_ENTITY_SPACE_ID,
                "title": "推荐免试研究生",
                "metadata_json": {
                    "entity_type": "admission_method",
                    "canonical_name": "推荐免试研究生",
                    "aliases": ["推荐免试研究生", "免试攻读研究生", "推免", "保研"],
                    "entity_metadata": {},
                },
                "score": 0.0,
            }
        ]
    )
    rag_backend = FakeRagBackend()
    agent = KBQueryAgent(
        rag_backend=rag_backend,
        analytics_engine=FakeAnalyticsEngine(),
        entity_resolver=EntityResolver(entity_backend),
    )

    await agent.retrieve(KnowledgeQuery(question="人工智能学院保研要求", space_id=""))

    assert rag_backend.calls[0]["space_ids"] == []
    rag_queries = rag_backend.calls[0]["queries"]
    assert rag_queries[0] == "人工智能学院保研要求"
    assert len(rag_queries) == 2
    assert "人工智能学院保研要求" in rag_queries[1]
    assert "推荐免试研究生" in rag_queries[1]
    assert "免试攻读研究生" in rag_queries[1]
    assert "推免" in rag_queries[1]


def test_rag_query_routes_ignore_low_confidence_entity_matches():
    queries = rag_query_routes(
        "保研要求",
        (
            EntityMatch(
                entity_id="weak",
                space_id="sai",
                entity_type="admission_method",
                canonical_name="推荐免试研究生",
                aliases=("推免", "保研"),
                score=42.0,
            ),
        ),
    )

    assert queries == ["保研要求"]
