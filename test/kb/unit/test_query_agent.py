from __future__ import annotations

import pytest

from luoying_bot.capabilities.knowledge_base.entity_resolver import EntityResolver
from luoying_bot.capabilities.knowledge_base.models import KnowledgeQuery
from luoying_bot.capabilities.knowledge_base.query_agent import (
    KBQueryAgent,
    KBQueryAgentConfig,
    rag_query_with_entities,
)
from luoying_bot.capabilities.knowledge_base.entities import EntityMatch

from _fakes import FakeEntityBackend, FakeRagBackend


class FakeAnalyticsEngine:
    async def query(self, query, entities):
        return []


@pytest.mark.asyncio
async def test_resolved_entity_aliases_expand_rag_query():
    entity_backend = FakeEntityBackend(
        items=[
            {
                "entity_id": "e_recommended_exemption",
                "space_id": "sai",
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
        config=KBQueryAgentConfig(default_space_id="sai"),
    )

    await agent.retrieve(KnowledgeQuery(question="保研要求", space_id="sai"))

    rag_query = rag_backend.calls[0]["query"]
    assert "保研要求" in rag_query
    assert "推荐免试研究生" in rag_query
    assert "免试攻读研究生" in rag_query
    assert "推免" in rag_query


def test_rag_query_expansion_ignores_low_confidence_entity_matches():
    query = rag_query_with_entities(
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

    assert query == "保研要求"
