from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SemanticTable:
    name: str
    description: str
    columns: tuple[str, ...]
    measures: tuple[str, ...] = ()
    dimensions: tuple[str, ...] = ()


class KnowledgeSemanticLayer:
    def __init__(self) -> None:
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
                measures=("view_count",),
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
            ),
        )

    @property
    def allowed_tables(self) -> set[str]:
        return {table.name for table in self._tables}

    def table_columns(self, table_name: str) -> tuple[str, ...]:
        for table in self._tables:
            if table.name == table_name:
                return table.columns
        return ()

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

    def is_analytics_question(self, question: str) -> bool:
        text = question.strip()
        return any(
            marker in text
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
                "哪个省",
                "哪一省",
                "最高",
                "最低",
                "专业",
                "学院",
                "学部",
                "栏目",
                "文章",
                "通知",
                "热点",
                "试验班",
                "视频",
                "宣传片",
            )
        )
