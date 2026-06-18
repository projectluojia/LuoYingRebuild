from __future__ import annotations

import re
from typing import Any

from luoying_bot.capabilities.knowledge_base.models import Citation, KnowledgeAnswer, KnowledgeQuery, StructuredRecord
from luoying_bot.capabilities.knowledge_base.ports import KnowledgeDomain, StructuredBackend


class AdmissionsKnowledgeDomain(KnowledgeDomain):
    name = "admissions"

    def __init__(
        self,
        *,
        dataset_id: str,
        collection_prefix: str = "",
    ):
        self.dataset_id = dataset_id
        self.collection_prefix = collection_prefix

    def dataset_id_for_space(self, space_id: str) -> str:
        return self.dataset_id or space_id

    def extract_filters(self, question: str, provided: dict[str, Any]) -> dict[str, Any]:
        filters = dict(provided)
        year = self._find_year(question)
        if year and not filters.get("year"):
            filters["year"] = year
        for province in self._known_provinces():
            if province in question and not filters.get("province"):
                filters["province"] = province
                break
        if "物理" in question and not filters.get("subject_type"):
            filters["subject_type"] = "物理"
        elif "历史" in question and not filters.get("subject_type"):
            filters["subject_type"] = "历史"
        elif "理科" in question and not filters.get("subject_type"):
            filters["subject_type"] = "理科"
        elif "文科" in question and not filters.get("subject_type"):
            filters["subject_type"] = "文科"
        return filters

    async def query_structured(
        self,
        backend: StructuredBackend,
        query: KnowledgeQuery,
    ) -> list[StructuredRecord]:
        collections = self._collections_for_question(query.question)
        records: list[StructuredRecord] = []
        for collection in collections:
            metadata_filter = self._metadata_filter(query, collection)
            items = await backend.list_items(
                self._collection(collection),
                filters=metadata_filter,
                limit=8,
                sort=["-year"] if collection in {"admission_scores", "admission_plans"} else None,
            )
            for item in items:
                records.append(
                    StructuredRecord(
                        collection=collection,
                        data=item,
                        citation=self._citation_from_item(item, collection),
                    )
                )
        return records

    def build_system_instruction(self, query: KnowledgeQuery) -> str:
        return (
            "你是学校招生知识库助手。分数线、位次、招生计划必须基于结构化资料；"
            "专业介绍、班型、就业前景必须基于已检索来源；不得承诺录取结果。"
        )

    def validate_answer(self, answer: KnowledgeAnswer) -> KnowledgeAnswer:
        if answer.answer and "录取" in answer.answer and "保证" in answer.answer:
            answer.answer += "\n\n提醒：录取结果受当年计划、报考人数和投档规则影响，不能作保证。"
        return answer

    def _collection(self, name: str) -> str:
        return f"{self.collection_prefix}{name}" if self.collection_prefix else name

    def _collections_for_question(self, question: str) -> list[str]:
        collections: list[str] = []
        if any(word in question for word in ("分数", "分数线", "位次", "最低分", "最高分", "平均分")):
            collections.append("admission_scores")
        if any(word in question for word in ("计划", "招多少", "招生人数", "名额", "学费", "学制")):
            collections.append("admission_plans")
        if any(word in question for word in ("专业", "课程", "学什么", "就业", "方向", "前景", "考研")):
            collections.append("majors")
        if any(word in question for word in ("班", "班型", "实验班", "卓越班", "拔尖")):
            collections.append("class_types")
        return collections or ["majors", "class_types"]

    def _metadata_filter(self, query: KnowledgeQuery, collection: str) -> dict[str, Any]:
        clauses: list[dict[str, Any]] = [
            {"review_status": {"_eq": "approved"}},
        ]
        if query.space_id:
            clauses.append({"space_id": {"_eq": query.space_id}})
        for key in ("year", "province", "subject_type", "batch"):
            value = query.filters.get(key)
            if value not in (None, ""):
                clauses.append({key: {"_eq": value}})
        major = query.filters.get("major_name") or query.filters.get("major")
        if major and collection in {"admission_scores", "admission_plans", "majors"}:
            clauses.append({"major_name" if collection != "majors" else "name": {"_contains": major}})
        return {"_and": clauses}

    def _citation_from_item(self, item: dict[str, Any], collection: str) -> Citation:
        title = str(
            item.get("title")
            or item.get("source_document")
            or item.get("name")
            or item.get("major_name")
            or collection
        )
        source = str(item.get("source_url") or item.get("source_document") or item.get("id") or "")
        snippet = str(item.get("source_text") or "")
        return Citation(
            title=title,
            source=source,
            snippet=snippet[:500],
            published_at=self._optional_text(item.get("published_at") or item.get("year")),
            department=self._optional_text(item.get("source_department")),
            metadata={"collection": collection, "id": item.get("id")},
        )

    def _find_year(self, question: str) -> int | None:
        match = re.search(r"(20\d{2})", question)
        if match:
            return int(match.group(1))
        if "去年" in question:
            from datetime import date

            return date.today().year - 1
        if "今年" in question:
            from datetime import date

            return date.today().year
        return None

    def _optional_text(self, value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    def _known_provinces(self) -> tuple[str, ...]:
        return (
            "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江",
            "上海", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南",
            "湖北", "湖南", "广东", "广西", "海南", "重庆", "四川", "贵州",
            "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆",
        )
