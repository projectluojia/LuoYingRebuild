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
        )

    @property
    def allowed_tables(self) -> set[str]:
        return {table.name for table in self._tables}

    def table_columns(self, table_name: str) -> tuple[str, ...]:
        for table in self._tables:
            if table.name == table_name:
                return table.columns
        return ()

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
            ("class_types", "name"),
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
            )
        )
