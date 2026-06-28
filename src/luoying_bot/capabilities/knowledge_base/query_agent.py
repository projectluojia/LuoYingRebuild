from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from luoying_bot.capabilities.knowledge_base.entity_resolver import EntityResolution, EntityResolver
from luoying_bot.capabilities.knowledge_base.entities import EntityMatch, normalize_entity_text
from luoying_bot.capabilities.knowledge_base.errors import BackendUnavailable
from luoying_bot.capabilities.knowledge_base.models import KnowledgeQuery, RetrievalResult, StructuredRecord
from luoying_bot.capabilities.knowledge_base.ports import RagBackend
from luoying_bot.capabilities.knowledge_base.semantic_layer import KnowledgeSemanticLayer
from luoying_bot.ports.llm import ChatModel


class AnalyticsEngine(Protocol):
    async def query(self, query: KnowledgeQuery, entities: EntityResolution | None = None) -> list[StructuredRecord]: ...


@dataclass(frozen=True, slots=True)
class RetrievalPlan:
    search_analytics: bool
    search_rag: bool
    rationale: str = ""


class KBRetrievalPlanner:
    def __init__(
        self,
        model: ChatModel,
        *,
        semantic_layer: KnowledgeSemanticLayer,
    ):
        self.model = model
        self.semantic_layer = semantic_layer

    async def plan(self, query: KnowledgeQuery, entities: EntityResolution) -> RetrievalPlan:
        raw = await self.model.chat(
            [
                {"role": "system", "content": "你是知识库检索规划子代理，只输出严格 JSON。"},
                {
                    "role": "user",
                    "content": RETRIEVAL_PLAN_PROMPT.format(
                        question=query.question,
                        semantic_schema=self.semantic_layer.prompt_context(),
                        resolved_entities=entities.prompt_context(),
                    ),
                },
            ],
            temperature=0.0,
        )
        return parse_retrieval_plan(raw)


class KBQueryAgent:
    def __init__(
        self,
        *,
        rag_backend: RagBackend,
        analytics_engine: AnalyticsEngine,
        entity_resolver: EntityResolver,
        retrieval_planner: KBRetrievalPlanner,
    ):
        self.rag_backend = rag_backend
        self.analytics_engine = analytics_engine
        self.entity_resolver = entity_resolver
        self.retrieval_planner = retrieval_planner

    async def retrieve(self, query: KnowledgeQuery) -> RetrievalResult:
        entities = await self.entity_resolver.resolve(query)
        plan = await self.retrieval_planner.plan(query, entities)
        structured_records = []
        if plan.search_analytics:
            structured_records = await self.analytics_engine.query(query, entities)
        chunks = []
        if plan.search_rag:
            chunks = await self.rag_backend.search(
                queries=rag_query_routes(query.question, entities.matches),
                space_ids=[],
                entity_matches=entities.matches,
                top_k=query.top_k,
            )
        return RetrievalResult(
            structured_records=structured_records,
            chunks=chunks,
        )


def rag_query_routes(question: str, matches: tuple[EntityMatch, ...], *, max_terms: int = 24) -> list[str]:
    routes = [question]
    expanded = expanded_rag_query(question, matches, max_terms=max_terms)
    if normalize_entity_text(expanded) != normalize_entity_text(question):
        routes.append(expanded)
    return routes


def expanded_rag_query(question: str, matches: tuple[EntityMatch, ...], *, max_terms: int = 24) -> str:
    terms: list[str] = []
    question_norm = normalize_entity_text(question)
    seen: set[str] = {question_norm}
    for match in matches:
        if not should_expand_rag_query(match):
            continue
        canonical_norm = normalize_entity_text(match.canonical_name)
        if canonical_norm and canonical_norm in question_norm:
            continue
        for term in [match.canonical_name, match.matched_alias, *match.aliases]:
            clean_term = term.strip()
            normalized = normalize_entity_text(clean_term)
            if not clean_term or not normalized or normalized in seen:
                continue
            seen.add(normalized)
            terms.append(clean_term)
            if len(terms) >= max_terms:
                break
        if len(terms) >= max_terms:
            break
    if not terms:
        return question
    return f"{question}\n实体别名：{' '.join(terms)}"


def should_expand_rag_query(match: EntityMatch) -> bool:
    return match.score >= 100.0 or match.alias_type == "relation_resolution"


RETRIEVAL_PLAN_PROMPT = """\
根据用户问题决定知识库检索计划。

结构化查询适用于数据库字段能直接回答的问题，例如分数、位次、招生计划人数、学院目录、专业目录、试验班目录。
RAG 文档检索适用于网页正文、通知、培养方案、课程内容、师资介绍、办事说明、页面位置、政策原文摘要。
可以同时启用两者；如果结构化表不直接覆盖问题，应关闭结构化查询。

可用结构化 schema：
{semantic_schema}

已解析实体：
{resolved_entities}

只输出 JSON：
{{"search_analytics":true|false,"search_rag":true|false,"rationale":"..."}}

用户问题：
{question}
"""


def parse_retrieval_plan(raw: str) -> RetrievalPlan:
    data = parse_json_object(raw)
    analytics = data.get("search_analytics")
    rag = data.get("search_rag")
    if not isinstance(analytics, bool) or not isinstance(rag, bool):
        raise BackendUnavailable("retrieval planner must return boolean search_analytics and search_rag")
    if not analytics and not rag:
        raise BackendUnavailable("retrieval planner disabled both analytics and rag")
    return RetrievalPlan(
        search_analytics=analytics,
        search_rag=rag,
        rationale=str(data.get("rationale") or "").strip(),
    )


def parse_json_object(raw: str) -> dict[str, object]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise BackendUnavailable("retrieval planner response is not JSON") from exc
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as nested_exc:
            raise BackendUnavailable("retrieval planner response is not valid JSON") from nested_exc
    if not isinstance(data, dict):
        raise BackendUnavailable("retrieval planner response must be a JSON object")
    return data
