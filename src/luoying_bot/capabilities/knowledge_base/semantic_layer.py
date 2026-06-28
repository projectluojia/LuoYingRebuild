from __future__ import annotations

from dataclasses import dataclass, field

from luoying_bot.capabilities.knowledge_base.text_utils import normalize_alnum_text


@dataclass(frozen=True, slots=True)
class SemanticLiteralFilter:
    field: str
    value: str
    aliases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SemanticTable:
    name: str
    description: str
    columns: tuple[str, ...]
    measures: tuple[str, ...] = ()
    dimensions: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    measure_aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    literal_filters: tuple[SemanticLiteralFilter, ...] = ()
    entity_fields: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class QueryLexicon:
    descending_aliases: tuple[str, ...] = ("最高", "最多", "最大")
    ascending_aliases: tuple[str, ...] = ("最低", "最少", "最小")
    subject_types: tuple[str, ...] = ("物理类", "历史类", "综合改革", "文史", "理工", "艺术类")


class KnowledgeSemanticLayer:
    def __init__(self) -> None:
        self.lexicon = QueryLexicon()
        self._tables = (
            SemanticTable(
                name="admission_scores",
                description="武汉大学历年分省、科类、批次、专业录取分数和位次。",
                columns=(
                    "space_id",
                    "year",
                    "province",
                    "subject_type",
                    "batch",
                    "major_name",
                    "min_score",
                    "max_score",
                    "avg_score",
                    "min_rank",
                    "source_url",
                    "source_document",
                    "source_department",
                    "published_at",
                    "review_status",
                ),
                dimensions=("year", "province", "subject_type", "batch", "major_name"),
                measures=("min_score", "max_score", "avg_score", "min_rank"),
                measure_aliases={
                    "min_score": ("分数线", "最低分", "录取分", "分数", "录取"),
                    "max_score": ("最高分",),
                    "avg_score": ("平均分",),
                    "min_rank": ("位次", "最低位次", "排名"),
                },
                entity_fields={"province": ("province",), "major": ("major_name",)},
            ),
            SemanticTable(
                name="admission_plans",
                description="武汉大学分省、科类、批次、专业招生计划人数。",
                columns=(
                    "space_id",
                    "year",
                    "province",
                    "subject_type",
                    "batch",
                    "major_name",
                    "class_type",
                    "plan_count",
                    "tuition",
                    "schooling_years",
                    "remarks",
                    "source_url",
                    "source_document",
                    "source_department",
                    "published_at",
                    "review_status",
                ),
                dimensions=("year", "province", "subject_type", "batch", "major_name", "class_type"),
                measures=("plan_count",),
                measure_aliases={"plan_count": ("招生计划", "招生人数", "计划人数", "招多少", "多少人")},
                entity_fields={"province": ("province",), "major": ("major_name",), "class_type": ("class_type",)},
            ),
            SemanticTable(
                name="admission_strong_foundation_scores",
                description="武汉大学强基计划分省录取最低分和最低位次。",
                columns=(
                    "space_id",
                    "year",
                    "province",
                    "program_name",
                    "subject_type",
                    "min_score",
                    "min_rank",
                    "source_url",
                    "source_document",
                    "source_department",
                    "published_at",
                    "review_status",
                ),
                dimensions=("year", "province", "program_name", "subject_type"),
                measures=("min_score", "min_rank"),
                measure_aliases={
                    "min_score": ("强基", "分数线", "最低分", "录取分", "分数", "录取"),
                    "min_rank": ("强基", "位次", "最低位次", "排名"),
                },
                entity_fields={"province": ("province",), "program": ("program_name",)},
            ),
            SemanticTable(
                name="majors",
                description="专业基础资料。",
                columns=(
                    "space_id",
                    "name",
                    "school_name",
                    "degree",
                    "category",
                    "source_url",
                    "source_document",
                    "source_department",
                    "published_at",
                    "review_status",
                ),
                dimensions=("name", "school_name", "degree", "category"),
                aliases=("专业", "本科专业"),
                entity_fields={"major": ("name",), "school": ("school_name",)},
            ),
            SemanticTable(
                name="class_types",
                description="班型、试验班等类型资料。",
                columns=(
                    "space_id",
                    "name",
                    "description",
                    "source_url",
                    "source_document",
                    "source_department",
                    "published_at",
                    "review_status",
                ),
                dimensions=("name",),
                aliases=("班型", "试验班"),
                entity_fields={"class_type": ("name",)},
            ),
            SemanticTable(
                name="admission_articles",
                description="武汉大学本科招生网文章、通知、热点内容及其栏目。",
                columns=(
                    "space_id",
                    "article_id",
                    "category_id",
                    "category_name",
                    "title",
                    "description",
                    "source_url",
                    "published_at",
                    "view_count",
                    "source_document",
                    "source_department",
                    "review_status",
                ),
                dimensions=("category_name", "title", "published_at"),
                aliases=("文章", "通知", "热点武大"),
                measures=("view_count",),
                measure_aliases={"view_count": ("浏览", "阅读", "热度")},
                literal_filters=(
                    SemanticLiteralFilter(field="category_name", value="热点武大", aliases=("热点武大",)),
                ),
            ),
            SemanticTable(
                name="academic_units",
                description="武汉大学本科招生网学部目录。",
                columns=(
                    "space_id",
                    "unit_id",
                    "name",
                    "sort_order",
                    "source_url",
                    "source_document",
                    "source_department",
                    "review_status",
                ),
                dimensions=("name",),
                aliases=("学部", "学部目录"),
            ),
            SemanticTable(
                name="admission_schools",
                description="武汉大学本科招生网学院目录，包含所属学部和学院官网。",
                columns=(
                    "space_id",
                    "school_id",
                    "unit_id",
                    "unit_name",
                    "name",
                    "official_url",
                    "source_url",
                    "source_document",
                    "source_department",
                    "review_status",
                ),
                dimensions=("unit_name", "name"),
                aliases=("学院", "学院目录", "学院官网"),
                entity_fields={"school": ("name",)},
            ),
            SemanticTable(
                name="admission_media_items",
                description="武汉大学本科招生网影像、专业介绍、试验班、宣传片等条目。",
                columns=(
                    "space_id",
                    "item_id",
                    "category_id",
                    "category_name",
                    "title",
                    "item_type",
                    "source_url",
                    "media_url",
                    "description",
                    "published_at",
                    "source_document",
                    "source_department",
                    "review_status",
                ),
                dimensions=("category_name", "title", "item_type"),
                aliases=("影像", "专题", "试验班", "宣传片"),
                literal_filters=(
                    SemanticLiteralFilter(field="category_name", value="试验班", aliases=("试验班",)),
                ),
            ),
        )

    @property
    def allowed_tables(self) -> set[str]:
        return {table.name for table in self._tables}

    def tables(self) -> tuple[SemanticTable, ...]:
        return self._tables

    def table(self, table_name: str) -> SemanticTable | None:
        for table in self._tables:
            if table.name == table_name:
                return table
        return None

    def table_columns(self, table_name: str) -> tuple[str, ...]:
        table = self.table(table_name)
        return table.columns if table else ()

    def choose_table(self, question: str, table_names: list[str]) -> str:
        candidates = [table for table in self._tables if table.name in table_names]
        ranked = sorted(candidates, key=lambda table: self.table_score(question, table), reverse=True)
        return ranked[0].name if ranked else ""

    def ranked_tables(self, question: str) -> list[SemanticTable]:
        ranked = sorted(self._tables, key=lambda table: self.table_score(question, table), reverse=True)
        return [table for table in ranked if self.table_score(question, table) > 0]

    def table_score(self, question: str, table: SemanticTable) -> float:
        question_norm = normalize_alnum_text(question)
        score = 0.0
        for alias_group in table.measure_aliases.values():
            for alias in alias_group:
                alias_norm = normalize_alnum_text(alias)
                if alias_norm and alias_norm in question_norm:
                    score += 4.0 + min(len(alias_norm), 8) / 4.0
        for literal_filter in table.literal_filters:
            for alias in literal_filter.aliases:
                alias_norm = normalize_alnum_text(alias)
                if alias_norm and alias_norm in question_norm:
                    score += 3.0 + min(len(alias_norm), 8) / 4.0
        for token in [table.name, table.description, *table.aliases, *table.dimensions, *table.measures]:
            token_norm = normalize_alnum_text(token)
            if token_norm and token_norm in question_norm:
                score += 1.0
        return score

    def metric_for_question(self, table_name: str, question: str) -> str:
        table = self.table(table_name)
        if table is None:
            return ""
        question_norm = normalize_alnum_text(question)
        best: tuple[float, str] = (0.0, "")
        for measure in table.measures:
            score = 0.0
            for alias in table.measure_aliases.get(measure, (measure,)):
                alias_norm = normalize_alnum_text(alias)
                if alias_norm and alias_norm in question_norm:
                    score += 4.0 + min(len(alias_norm), 8) / 4.0
            measure_norm = normalize_alnum_text(measure)
            if measure_norm and measure_norm in question_norm:
                score += 2.0
            if score > best[0]:
                best = (score, measure)
        return best[1]

    def metric_label(self, table_name: str, metric: str) -> str:
        table = self.table(table_name)
        if table is None or not metric:
            return metric
        aliases = table.measure_aliases.get(metric) or ()
        return aliases[0] if aliases else metric

    def order_by_for_question(self, table_name: str, question: str) -> str:
        table = self.table(table_name)
        metric = self.metric_for_question(table_name, question)
        if table is None or not metric:
            return ""
        direction = "desc" if self.has_any_alias(question, self.lexicon.descending_aliases) else "asc"
        tie_breakers = [dimension for dimension in table.dimensions if dimension in table.columns and dimension != metric]
        suffix = ", ".join(f"{column} asc" for column in tie_breakers[:3])
        order = f"{metric} {direction} nulls last"
        return f"{order}, {suffix}" if suffix else order

    def subject_type(self, question: str) -> str:
        question_norm = normalize_alnum_text(question)
        for subject_type in self.lexicon.subject_types:
            if normalize_alnum_text(subject_type) in question_norm:
                return subject_type
        return ""

    def literal_filter_clauses(self, table: SemanticTable, question: str) -> list[tuple[str, str]]:
        question_norm = normalize_alnum_text(question)
        filters: list[tuple[str, str]] = []
        for item in table.literal_filters:
            if any(normalize_alnum_text(alias) in question_norm for alias in item.aliases):
                filters.append((item.field, item.value))
        return filters

    def entity_fields(self, table_name: str, entity_type: str) -> tuple[str, ...]:
        table = self.table(table_name)
        if table is None:
            return ()
        return table.entity_fields.get(entity_type, ())

    def has_any_alias(self, question: str, aliases: tuple[str, ...]) -> bool:
        question_norm = normalize_alnum_text(question)
        return any(normalize_alnum_text(alias) in question_norm for alias in aliases)

    def filter_fields_by_table(self) -> dict[str, set[str]]:
        return {table.name: set(table.columns) for table in self._tables}

    def prompt_context(self) -> str:
        blocks: list[str] = []
        for table in self._tables:
            blocks.append(
                "\n".join(
                    [
                        f"Table: {table.name}",
                        f"Description: {table.description}",
                        f"Columns: {', '.join(table.columns)}",
                        f"Dimensions: {', '.join(table.dimensions) or 'none'}",
                        f"Measures: {', '.join(table.measures) or 'none'}",
                    ]
                )
            )
        return "\n\n".join(blocks)

    def semantic_rules(self) -> str:
        return "\n".join(
            [
                "分数线、最低分、录取分一般对应 admission_scores.min_score。",
                "强基计划、数学与应用数学（智能科学）强基计划对应 admission_strong_foundation_scores；不要用 admission_scores 代替。",
                "最高分对应 admission_scores.max_score；平均分对应 admission_scores.avg_score；位次对应 admission_scores.min_rank。",
                "招生人数、招多少人、计划人数对应 admission_plans.plan_count。",
                "省份比较问题按 province 分组或直接返回 province 字段；最高按相关 measure 降序排序。",
                "用户问“哪个最高、哪一省最高、最高的是谁”时默认只返回第一名；问“最低”同理只返回第一名。",
                "专业、班型、试验班等名称通常在 major_name 或 class_type 中；不确定精确名称时使用 ILIKE 模糊过滤。",
                "所有结构化表都有 review_status，正式查询必须包含 review_status = 'approved'。",
                "结果必须保留 source_url、source_document、source_department、published_at，以便回答引用来源。",
            ]
        )

    def value_hint_fields(self) -> tuple[tuple[str, str], ...]:
        return (
            ("admission_scores", "province"),
            ("admission_scores", "subject_type"),
            ("admission_scores", "batch"),
            ("admission_scores", "major_name"),
            ("admission_plans", "province"),
            ("admission_plans", "subject_type"),
            ("admission_plans", "batch"),
            ("admission_plans", "major_name"),
            ("admission_plans", "class_type"),
            ("admission_strong_foundation_scores", "province"),
            ("admission_strong_foundation_scores", "program_name"),
            ("majors", "name"),
            ("majors", "school_name"),
            ("class_types", "name"),
            ("admission_articles", "category_name"),
            ("admission_articles", "title"),
            ("academic_units", "name"),
            ("admission_schools", "unit_name"),
            ("admission_schools", "name"),
            ("admission_media_items", "category_name"),
            ("admission_media_items", "title"),
        )
