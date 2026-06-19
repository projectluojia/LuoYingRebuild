from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from luoying_bot.capabilities.knowledge_base.models import Citation, KnowledgeQuery, StructuredRecord
from luoying_bot.capabilities.knowledge_base.ports import AnalyticsBackend, StructuredBackend
from luoying_bot.capabilities.knowledge_base.semantic_layer import KnowledgeSemanticLayer
from luoying_bot.ports.llm import ChatModel


@dataclass(slots=True)
class AnalyticsPlan:
    sql: str
    rationale: str = ""


class KnowledgeAnalyticsEngine:
    def __init__(
        self,
        *,
        backend: AnalyticsBackend,
        value_backend: StructuredBackend,
        model: ChatModel,
        semantic_layer: KnowledgeSemanticLayer,
        max_rows: int = 12,
    ):
        self.backend = backend
        self.value_backend = value_backend
        self.model = model
        self.semantic_layer = semantic_layer
        self.max_rows = max_rows

    async def query(self, query: KnowledgeQuery) -> list[StructuredRecord]:
        if not self.semantic_layer.is_analytics_question(query.question):
            return []
        plan = await self._plan(query)
        if not plan.sql:
            return []
        safe_sql = validate_select_sql(
            plan.sql,
            allowed_tables=self.semantic_layer.allowed_tables,
            max_rows=self.max_rows,
        )
        rows = await self.backend.execute_select(safe_sql, limit=self.max_rows)
        return [
            StructuredRecord(
                collection="analytics",
                data={**row, "_sql": safe_sql, "_rationale": plan.rationale},
                citation=citation_from_row(row),
                score=1.0,
            )
            for row in rows
        ]

    async def _plan(self, query: KnowledgeQuery) -> AnalyticsPlan:
        candidate_values = await self._candidate_values(query.question)
        prompt = ANALYTICS_PROMPT.format(
            semantic_schema=self.semantic_layer.prompt_context(),
            semantic_rules=self.semantic_layer.semantic_rules(),
            candidate_values=candidate_values or "无",
            max_rows=self.max_rows,
            question=query.question,
            space_filter=f"space_id = '{query.space_id}'" if query.space_id else "按问题语义决定；不确定时不要强行限制 space_id",
        )
        raw = await self.model.chat(
            [
                {"role": "system", "content": "你是知识库结构化查询规划器，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        data = parse_json_object(raw)
        sql = str(data.get("sql") or "").strip()
        rationale = str(data.get("rationale") or "").strip()
        return AnalyticsPlan(sql=sql, rationale=rationale)

    async def _candidate_values(self, question: str) -> str:
        query_norm = normalize_text(question)
        lines: list[str] = []
        for table, field in self.semantic_layer.value_hint_fields():
            values = await self.value_backend.distinct_values(table, field, limit=20000)
            matched = rank_candidate_values(query_norm=query_norm, values=values)
            if matched:
                lines.append(f"{table}.{field}: {', '.join(matched[:12])}")
        return "\n".join(lines)


ANALYTICS_PROMPT = """\
你要把用户问题转换成一个只读 PostgreSQL SELECT 查询。

可用语义表：
{semantic_schema}

语义规则：
{semantic_rules}

从数据库真实值中检索到的候选字段值：
{candidate_values}

约束：
- 只允许 SELECT。
- 只允许查询上述表。
- 不要修改数据，不要调用函数产生副作用。
- 不要输出 Markdown。
- 只输出 JSON：{{"sql":"...","rationale":"..."}}。
- 如果问题不适合结构化查询，输出 {{"sql":"","rationale":"not_structured"}}。
- SQL 必须限制最多 {max_rows} 行。
- 当前 space 过滤：{space_filter}。

用户问题：
{question}
"""


FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|copy|call|execute|merge|refresh|vacuum|analyze)\b",
    re.IGNORECASE,
)
TABLE_REF = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)
LIMIT_REF = re.compile(r"\blimit\s+(\d+)\b", re.IGNORECASE)


def validate_select_sql(sql: str, *, allowed_tables: set[str], max_rows: int) -> str:
    clean = strip_sql(sql)
    lowered = clean.lower()
    if not lowered.startswith("select "):
        raise ValueError("analytics SQL must start with SELECT")
    if ";" in clean or "--" in clean or "/*" in clean or "*/" in clean:
        raise ValueError("analytics SQL must be a single uncommented statement")
    if FORBIDDEN_SQL.search(clean):
        raise ValueError("analytics SQL contains forbidden operation")
    tables = {match.group(1).lower() for match in TABLE_REF.finditer(clean)}
    if not tables:
        raise ValueError("analytics SQL must reference at least one table")
    disallowed = tables - {table.lower() for table in allowed_tables}
    if disallowed:
        raise ValueError(f"analytics SQL references disallowed tables: {', '.join(sorted(disallowed))}")
    return enforce_limit(clean, max_rows=max_rows)


def strip_sql(sql: str) -> str:
    text = sql.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:sql)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    return text.rstrip(";").strip()


def enforce_limit(sql: str, *, max_rows: int) -> str:
    match = LIMIT_REF.search(sql)
    if not match:
        return f"select * from ({sql}) as kb_analytics_result limit {max_rows}"
    limit = int(match.group(1))
    if limit <= max_rows:
        return sql
    start, end = match.span(1)
    return f"{sql[:start]}{max_rows}{sql[end:]}"


def parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}


def citation_from_row(row: dict[str, Any]) -> Citation:
    title = str(
        row.get("source_document")
        or row.get("program_name")
        or row.get("major_name")
        or row.get("name")
        or "结构化知识库"
    )
    source = str(row.get("source_url") or "")
    return Citation(
        title=title,
        source=source,
        published_at=optional_text(row.get("published_at") or row.get("year")),
        department=optional_text(row.get("source_department")),
        metadata={"collection": "analytics"},
    )


def optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def rank_candidate_values(*, query_norm: str, values: list[str]) -> list[str]:
    scored: list[tuple[int, str]] = []
    for value in values:
        aliases = value_aliases(value)
        score = max((candidate_score(alias, query_norm) for alias in aliases), default=0)
        if score:
            scored.append((score, value))
    scored.sort(key=lambda item: (item[0], len(normalize_text(item[1]))), reverse=True)
    result: list[str] = []
    seen: set[str] = set()
    for _, value in scored:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def value_aliases(value: str) -> tuple[str, ...]:
    normalized = normalize_text(value)
    aliases = {normalized} if normalized else set()
    for group in re.findall(r"[（(]([^（）()]+)[）)]", str(value)):
        group_norm = normalize_text(group)
        if group_norm:
            aliases.add(group_norm)
    return tuple(alias for alias in aliases if alias)


def candidate_score(alias: str, query_norm: str) -> int:
    if not alias or not query_norm:
        return 0
    if alias in query_norm:
        return 100 + len(alias)
    overlap = longest_common_substring_length(alias, query_norm)
    return overlap if overlap >= 3 else 0


def normalize_text(value: str) -> str:
    return "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", str(value).lower()))


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
