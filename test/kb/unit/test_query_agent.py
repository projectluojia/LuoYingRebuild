from __future__ import annotations

import pytest

from luoying_bot.capabilities.knowledge_base.entity_resolver import EntityResolution, EntityResolver, entity_from_search_item
from luoying_bot.capabilities.knowledge_base.models import KnowledgeQuery, StructuredRecord
from luoying_bot.capabilities.knowledge_base.query_agent import (
    KBQueryAgent,
    RetrievalPlan,
    parse_retrieval_plan,
    rag_query_routes,
)
from luoying_bot.capabilities.knowledge_base.entities import GLOBAL_ENTITY_SPACE_ID, EntityMatch

from _fakes import FakeEntityBackend, FakeRagBackend


class FakeAnalyticsEngine:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    async def query(self, query: KnowledgeQuery, entities: EntityResolution | None = None) -> list[StructuredRecord]:
        self.calls.append({"query": query, "entities": entities})
        return []


class FakeRetrievalPlanner:
    def __init__(self, plan: RetrievalPlan):
        self._plan = plan
        self.calls: list[dict[str, object]] = []

    async def plan(self, query: KnowledgeQuery, entities: EntityResolution) -> RetrievalPlan:
        self.calls.append({"query": query, "entities": entities})
        return self._plan


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
        retrieval_planner=FakeRetrievalPlanner(
            RetrievalPlan(search_analytics=False, search_rag=True)
        ),
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


@pytest.mark.asyncio
async def test_rag_search_always_uses_all_spaces():
    entity_backend = FakeEntityBackend()
    rag_backend = FakeRagBackend()
    analytics = FakeAnalyticsEngine()
    agent = KBQueryAgent(
        rag_backend=rag_backend,
        analytics_engine=analytics,
        entity_resolver=EntityResolver(entity_backend),
        retrieval_planner=FakeRetrievalPlanner(
            RetrievalPlan(search_analytics=False, search_rag=True)
        ),
    )

    await agent.retrieve(KnowledgeQuery(question="师资力量", space_id="sai"))

    assert analytics.calls == []
    assert rag_backend.calls[0]["space_ids"] == []


@pytest.mark.asyncio
async def test_retrieval_planner_can_disable_rag_for_structured_query():
    entity_backend = FakeEntityBackend()
    rag_backend = FakeRagBackend()
    analytics = FakeAnalyticsEngine()
    agent = KBQueryAgent(
        rag_backend=rag_backend,
        analytics_engine=analytics,
        entity_resolver=EntityResolver(entity_backend),
        retrieval_planner=FakeRetrievalPlanner(
            RetrievalPlan(search_analytics=True, search_rag=False)
        ),
    )

    await agent.retrieve(KnowledgeQuery(question="湖北录取分数线", space_id=""))

    assert len(analytics.calls) == 1
    assert rag_backend.calls == []


def test_parse_retrieval_plan_ignores_space_ids():
    plan = parse_retrieval_plan(
        '{"search_analytics":false,"search_rag":true,"space_ids":["sai"],"rationale":"文档问题"}'
    )

    assert plan == RetrievalPlan(
        search_analytics=False,
        search_rag=True,
        rationale="文档问题",
    )


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


def test_entity_search_score_is_not_high_confidence_without_exact_alias_match():
    match = entity_from_search_item(
        {
            "entity_id": "program_1",
            "space_id": "whu",
            "title": "数学与应用数学（智能科学）强基计划",
            "metadata_json": {
                "entity_type": "program",
                "canonical_name": "数学与应用数学（智能科学）强基计划",
                "aliases": ["强基计划"],
                "entity_metadata": {"fact_table": "admission_strong_foundation_scores"},
            },
            "score": 512.0,
        },
        "武汉大学有哪些学部？",
    )

    assert match.score < 100.0
