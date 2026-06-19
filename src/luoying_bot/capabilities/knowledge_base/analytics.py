from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from luoying_bot.capabilities.knowledge_base.entity_resolver import EntityResolution
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
        max_rows: int = 50,
    ):
        self.backend = backend
        self.value_backend = value_backend
        self.model = model
        self.semantic_layer = semantic_layer
        self.max_rows = max_rows

    async def query(self, query: KnowledgeQuery, entities: EntityResolution | None = None) -> list[StructuredRecord]:
        if not self.semantic_layer.is_analytics_question(query.question):
            return []
        plan = self._site_content_plan(query, entities)
        if plan is None:
            plan = self._entity_plan(query, entities) if entities else None
        if plan is None:
            plan = await self._plan(query, entities)
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

    def _entity_plan(self, query: KnowledgeQuery, entities: EntityResolution | None) -> AnalyticsPlan | None:
        if entities is None:
            return None
        for entity in entities.matches:
            table = str(entity.metadata.get("fact_table") or "")
            fact_tables = [str(item) for item in entity.metadata.get("fact_tables") or []]
            field = str(entity.metadata.get("fact_column") or "")
            if not table and fact_tables and entity.score >= 100.0:
                table = choose_fact_table(query.question, fact_tables)
            if table not in self.semantic_layer.allowed_tables or field not in self.semantic_layer.table_columns(table):
                continue
            columns = self.semantic_layer.table_columns(table)
            select_columns = ", ".join(columns)
            clauses = [
                "review_status = 'approved'",
                f"{field} = {sql_literal(entity.canonical_name)}",
            ]
            if query.space_id:
                clauses.append(f"space_id = {sql_literal(query.space_id)}")
            year = extract_year(query.question)
            if year:
                clauses.append(f"year = {year}")
            subject_type = extract_subject_type(query.question)
            if subject_type and "subject_type" in columns:
                clauses.append(f"subject_type = {sql_literal(subject_type)}")
            question_norm = normalize_text(query.question)
            for province in entities.by_type("province"):
                province_norm = normalize_text(province.canonical_name)
                alias_norm = normalize_text(province.matched_alias)
                if province_norm not in question_norm and alias_norm not in question_norm:
                    continue
                clauses.append(f"province = {sql_literal(province.canonical_name)}")
                break
            order_by = "id asc"
            limit = 1
            if wants_highest(query.question) and "min_score" in columns:
                order_by = "min_score desc nulls last, min_rank asc nulls last, province asc"
            elif wants_lowest(query.question) and "min_score" in columns:
                order_by = "min_score asc nulls last, min_rank asc nulls last, province asc"
            if wants_listing(query.question):
                limit = self.max_rows
                if not (wants_highest(query.question) or wants_lowest(query.question)):
                    order_by = "province asc"
            sql = (
                f"select {select_columns} from {table} "
                f"where {' and '.join(clauses)} "
                f"order by {order_by} limit {limit}"
            )
            return AnalyticsPlan(sql=sql, rationale="entity_grounded")
        return None

    def _site_content_plan(self, query: KnowledgeQuery, entities: EntityResolution | None) -> AnalyticsPlan | None:
        question = query.question
        if is_fact_metric_question(question):
            return None
        clauses = ["review_status = 'approved'"]
        if query.space_id:
            clauses.append(f"space_id = {sql_literal(query.space_id)}")
        if "试验班" in question:
            where = " and ".join([*clauses, "category_name = '试验班'"])
            sql = (
                "select space_id, category_name, title, item_type, source_url, media_url, description, "
                "published_at, source_document, source_department, review_status "
                "from admission_media_items "
                f"where {where} "
                "order by title asc "
                f"limit {self.max_rows}"
            )
            return AnalyticsPlan(sql=sql, rationale="site_media_category")
        if "热点武大" in question:
            where = " and ".join([*clauses, "category_name = '热点武大'"])
            sql = (
                "select space_id, category_name, title, description, source_url, published_at, "
                "view_count, source_document, source_department, review_status "
                "from admission_articles "
                f"where {where} "
                "order by published_at desc nulls last, title asc "
                f"limit {self.max_rows}"
            )
            return AnalyticsPlan(sql=sql, rationale="site_article_category")
        if "学部" in question and entities:
            for school in entities.by_type("school"):
                where = " and ".join([*clauses, f"name = {sql_literal(school.canonical_name)}"])
                sql = (
                    "select space_id, unit_name, name, official_url, source_url, source_document, "
                    "source_department, review_status "
                    "from admission_schools "
                    f"where {where} "
                    "order by name asc "
                    "limit 1"
                )
                return AnalyticsPlan(sql=sql, rationale="site_school_unit")
        if "学院" in question and ("哪些" in question or "有哪些" in question or "列" in question):
            sql = (
                "select space_id, unit_name, name, official_url, source_url, source_document, "
                "source_department, review_status "
                "from admission_schools "
                f"where {' and '.join(clauses)} "
                "order by unit_name asc, name asc "
                f"limit {self.max_rows}"
            )
            return AnalyticsPlan(sql=sql, rationale="site_school_listing")
        if "专业" in question and ("哪些" in question or "有哪些" in question or "列" in question):
            sql = (
                "select space_id, name, school_name, category, source_url, source_document, "
                "source_department, review_status "
                "from majors "
                f"where {' and '.join(clauses)} "
                "order by school_name asc, name asc "
                f"limit {self.max_rows}"
            )
            return AnalyticsPlan(sql=sql, rationale="site_major_listing")
        return None

    async def _plan(self, query: KnowledgeQuery, entities: EntityResolution | None) -> AnalyticsPlan:
        candidate_values = await self._candidate_values(query.question)
        prompt = ANALYTICS_PROMPT.format(
            semantic_schema=self.semantic_layer.prompt_context(),
            semantic_rules=self.semantic_layer.semantic_rules(),
            candidate_values=candidate_values or "无",
            resolved_entities=entities.prompt_context() if entities else "无",
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

已解析实体：
{resolved_entities}

约束：
- 只允许 SELECT。
- 只允许查询上述表。
- 不要修改数据，不要调用函数产生副作用。
- 不要输出 Markdown。
- 只输出 JSON：{{"sql":"...","rationale":"..."}}。
- 如果问题不适合结构化查询，输出 {{"sql":"","rationale":"not_structured"}}。
- 已解析实体优先于用户原始说法；实体含 fact_table/fact_column 时必须优先使用对应表和字段。
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


def extract_year(question: str) -> int | None:
    match = re.search(r"(20\d{2})\s*年?", question)
    if match:
        return int(match.group(1))
    short = re.search(r"(?<!\d)(\d{2})\s*年", question)
    if not short:
        return None
    year = int(short.group(1))
    return 2000 + year if year < 80 else 1900 + year


def wants_listing(question: str) -> bool:
    return any(marker in question for marker in ("所有", "全部", "列出", "列给", "列一下", "明细", "各省"))


def choose_fact_table(question: str, fact_tables: list[str]) -> str:
    if any(marker in question for marker in ("招生计划", "招生人数", "计划人数", "招多少", "多少人")):
        if "admission_plans" in fact_tables:
            return "admission_plans"
    if any(marker in question for marker in ("分数", "分数线", "最低分", "最高分", "平均分", "位次", "录取")):
        if "admission_scores" in fact_tables:
            return "admission_scores"
    return fact_tables[0] if fact_tables else ""


def extract_subject_type(question: str) -> str:
    for subject_type in ("物理类", "历史类", "综合改革", "文史", "理工", "艺术类"):
        if subject_type in question:
            return subject_type
    return ""


def is_fact_metric_question(question: str) -> bool:
    return any(
        marker in question
        for marker in (
            "分数",
            "分数线",
            "最低分",
            "最高分",
            "平均分",
            "位次",
            "录取",
            "强基",
            "招生计划",
            "招生人数",
            "计划人数",
            "招多少",
            "多少人",
        )
    )


def wants_highest(question: str) -> bool:
    return "最高" in question or "最高分" in question


def wants_lowest(question: str) -> bool:
    return "最低" in question or "最低分" in question


def sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


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
