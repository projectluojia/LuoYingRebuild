from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import httpx
from openpyxl import load_workbook

from luoying_bot.capabilities.knowledge_base.artifacts import MarkdownArtifactStore
from luoying_bot.capabilities.knowledge_base.embeddings import OpenAICompatibleEmbeddingProvider
from luoying_bot.capabilities.knowledge_base.entities import normalize_entity_text, stable_entity_id, stable_search_item_id
from luoying_bot.capabilities.knowledge_base.postgres_store import IndexedDocument, PostgresKnowledgeStore
from luoying_bot.capabilities.knowledge_base.quality import MarkdownQualityChecker
from luoying_bot.config import settings


BASE_URL = "https://zsdata.whu.edu.cn/wzgl/wxmini"
SOURCE_URL = "https://zsdata.whu.edu.cn/public/wzgl/#/jhcx"
SITE_ID = "whu_admissions"
SPACE_ID = "whu"
STRONG_FOUNDATION_XLSX = Path("docs/2025分省（区）录取分数及位次 - 挂网 - 最新.xlsx")
STRONG_FOUNDATION_PROGRAM = "数学与应用数学（智能科学）强基计划"
ENTITY_SEED_PATH = Path("knowledge/seeds/whu_admissions_entities.json")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Import real WHU admission plan and score data into the KB")
    parser.add_argument("--province", default="", help="Optional province filter, for example 湖北")
    parser.add_argument("--year", default="", help="Optional year filter, for example 2025")
    parser.add_argument("--subject-type", default="", help="Optional subject filter, for example 物理类")
    parser.add_argument(
        "--strong-foundation-xlsx",
        default=str(STRONG_FOUNDATION_XLSX),
        help="Excel source for strong foundation score data",
    )
    parser.add_argument(
        "--entity-seed",
        default=str(ENTITY_SEED_PATH),
        help="Curated entity and alias seed file",
    )
    args = parser.parse_args()

    store = PostgresKnowledgeStore(
        settings.kb_database_url,
        embedding_provider=OpenAICompatibleEmbeddingProvider(
            base_url=settings.kb_embedding_base_url,
            api_key=settings.kb_embedding_api_key,
            model=settings.kb_embedding_model,
            batch_size=settings.kb_embedding_batch_size,
        ),
        embedding_dimensions=settings.kb_embedding_dimensions,
    )
    await store.ensure_schema()

    async with httpx.AsyncClient(verify=False, trust_env=False, timeout=30) as client:
        plan_rows, plan_raw = await fetch_rows(
            client,
            data_type="zsjh",
            province=args.province,
            year=args.year,
            subject_type=args.subject_type,
        )
        score_rows, score_raw = await fetch_rows(
            client,
            data_type="lnfs",
            province=args.province,
            year=args.year,
            subject_type=args.subject_type,
        )

    normalized_plans = normalize_plan_rows(plan_rows)
    normalized_scores = normalize_score_rows(score_rows)
    normalized_strong_foundation_scores = normalize_strong_foundation_rows(
        Path(args.strong_foundation_xlsx),
        year_filter=args.year,
        province_filter=args.province,
        subject_type_filter=args.subject_type,
    )
    imported_plans = await store.upsert_admission_plans(normalized_plans)
    imported_scores = await store.upsert_admission_scores(normalized_scores)
    imported_strong_foundation_scores = await store.upsert_admission_strong_foundation_scores(
        normalized_strong_foundation_scores
    )
    entity_payload = build_admission_entities(
        plans=normalized_plans,
        scores=normalized_scores,
        strong_foundation_scores=normalized_strong_foundation_scores,
        seed_path=Path(args.entity_seed),
    )
    await store.clear_kb_entities(SPACE_ID)
    imported_entities = await store.upsert_kb_entities(entity_payload["entities"])
    imported_entity_aliases = await store.upsert_kb_entity_aliases(entity_payload["aliases"])
    imported_entity_relations = await store.upsert_kb_entity_relations(entity_payload["relations"])
    search_items = build_search_items(
        entity_payload=entity_payload,
        plans=normalized_plans,
        scores=normalized_scores,
        strong_foundation_scores=normalized_strong_foundation_scores,
    )
    await store.clear_kb_search_items(SPACE_ID)
    imported_search_items = await store.upsert_kb_search_items(search_items)

    artifact_store = MarkdownArtifactStore(settings.kb_artifact_root)
    artifact_store.write_source(
        {
            "site_id": SITE_ID,
            "name": "武汉大学本科招生数据",
            "base_url": SOURCE_URL,
            "space_id": SPACE_ID,
            "allowed_domains": ["zsdata.whu.edu.cn"],
            "entry_urls": [SOURCE_URL],
            "updated_at": now_iso(),
            "data_api": f"{BASE_URL}/api/front/lqxx/getList",
        }
    )
    plan_artifact = write_dataset_artifact(
        artifact_store,
        title="武汉大学本科招生计划",
        url=f"{SOURCE_URL}?dataset=zsjh",
        rows=normalized_plans,
        raw_payload=plan_raw,
        row_markdown=plan_row_markdown,
    )
    score_artifact = write_dataset_artifact(
        artifact_store,
        title="武汉大学历年录取分数",
        url=f"{SOURCE_URL}?dataset=lnfs",
        rows=normalized_scores,
        raw_payload=score_raw,
        row_markdown=score_row_markdown,
    )
    strong_foundation_artifact = write_dataset_artifact(
        artifact_store,
        title="武汉大学强基计划录取分数",
        url=f"{SOURCE_URL}?dataset=strong_foundation",
        rows=normalized_strong_foundation_scores,
        raw_payload=[
            {
                "source_file": str(Path(args.strong_foundation_xlsx)),
                "program_name": STRONG_FOUNDATION_PROGRAM,
                "rows": normalized_strong_foundation_scores,
            }
        ],
        row_markdown=strong_foundation_row_markdown,
    )
    await index_artifact(store, plan_artifact)
    await index_artifact(store, score_artifact)
    if normalized_strong_foundation_scores:
        await index_artifact(store, strong_foundation_artifact)

    print(
        json.dumps(
            {
                "ok": True,
                "plans_imported": imported_plans,
                "scores_imported": imported_scores,
                "strong_foundation_scores_imported": imported_strong_foundation_scores,
                "entities_imported": imported_entities,
                "entity_aliases_imported": imported_entity_aliases,
                "entity_relations_imported": imported_entity_relations,
                "search_items_imported": imported_search_items,
                "plan_raw_requests": len(plan_raw),
                "score_raw_requests": len(score_raw),
                "artifact_root": str(settings.kb_artifact_root),
                "database_url": settings.kb_database_url,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


async def fetch_rows(
    client: httpx.AsyncClient,
    *,
    data_type: str,
    province: str,
    year: str,
    subject_type: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    type_payload = await post_api(client, "/api/front/lqxx/getType", {"type": data_type})
    type_map = type_payload.get("typeMap")
    if not isinstance(type_map, dict):
        raise ValueError(f"{data_type} getType returned no typeMap")
    rows: list[dict[str, Any]] = []
    raw_payloads: list[dict[str, Any]] = [{"endpoint": "getType", "data_type": data_type, "payload": type_payload}]
    seen_queries: set[tuple[str, str, str, str]] = set()
    for query in iter_queries(type_map, data_type=data_type, province=province, year=year, subject_type=subject_type):
        query_key = (query["sf"], query["nf"], query["klmc"], query["xqmc"])
        if query_key in seen_queries:
            continue
        seen_queries.add(query_key)
        payload = await post_api(client, "/api/front/lqxx/getList", query)
        raw_payloads.append({"endpoint": "getList", "data_type": data_type, "query": query, "payload": payload})
        payload_rows = payload.get("list") or payload.get("data") or []
        if not isinstance(payload_rows, list):
            continue
        rows.extend(row for row in payload_rows if isinstance(row, dict))
    return rows, raw_payloads


async def post_api(client: httpx.AsyncClient, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(
        f"{BASE_URL}{path}",
        json=payload,
        headers={
            "Content-Type": "application/json;charset=utf-8",
        },
    )
    response.raise_for_status()
    data = response.json()
    if int(data.get("code") or 0) != 200:
        raise ValueError(f"{path} failed: {data}")
    return data


def iter_queries(
    type_map: dict[str, Any],
    *,
    data_type: str,
    province: str,
    year: str,
    subject_type: str,
) -> Iterable[dict[str, str]]:
    for key in sorted(type_map):
        parts = key.split("_")
        if len(parts) != 4:
            continue
        sf, nf, klmc, xqmc = parts
        if klmc == "全部":
            continue
        if province and sf != province:
            continue
        if year and nf != year:
            continue
        if subject_type and klmc != subject_type:
            continue
        yield {
            "type": data_type,
            "sf": sf,
            "nf": nf,
            "zslb": "全部",
            "klmc": klmc,
            "xqmc": "" if xqmc in {"全部", "本校区", "校本部"} else xqmc,
        }


def normalize_plan_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        normalized = {
            "space_id": SPACE_ID,
            "year": as_int(row.get("nf")),
            "province": clean(row.get("sf")),
            "subject_type": clean(row.get("klmc")),
            "batch": clean(row.get("zslb") or row.get("pcmc")),
            "major_name": clean(row.get("zymc")),
            "class_type": clean(row.get("zslb")),
            "plan_count": as_int(row.get("jhrs")),
            "tuition": clean(row.get("zyxf")),
            "schooling_years": clean(row.get("xzmc")),
            "remarks": plan_remarks(row),
            "source_url": SOURCE_URL,
            "source_document": "武汉大学本科招生计划查询",
            "source_text": plan_row_markdown(row_to_plan(normalized_source=row)),
            "source_department": "武汉大学本科招生办公室",
            "published_at": clean(row.get("nf")),
            "raw_json": row,
        }
        if not normalized["year"] or not normalized["province"] or not normalized["subject_type"] or not normalized["major_name"]:
            continue
        key = (
            normalized["space_id"],
            normalized["year"],
            normalized["province"],
            normalized["subject_type"],
            normalized["batch"],
            normalized["major_name"],
            normalized["class_type"],
        )
        unique[key] = normalized
    return list(unique.values())


def normalize_score_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        normalized = {
            "space_id": SPACE_ID,
            "year": as_int(row.get("nf")),
            "province": clean(row.get("sf")),
            "subject_type": clean(row.get("klmc")),
            "batch": clean(row.get("zslb") or row.get("pcmc")),
            "major_name": clean(row.get("zymc")),
            "min_score": as_float(row.get("zdf")),
            "max_score": as_float(row.get("zgf")),
            "avg_score": as_float(row.get("pjf")),
            "min_rank": as_int(row.get("zdfwc")),
            "source_url": SOURCE_URL,
            "source_document": "武汉大学历年分数查询",
            "source_text": score_row_markdown(row_to_score(normalized_source=row)),
            "source_department": "武汉大学本科招生办公室",
            "published_at": clean(row.get("nf")),
            "raw_json": row,
        }
        if not normalized["year"] or not normalized["province"] or not normalized["subject_type"] or not normalized["major_name"]:
            continue
        key = (
            normalized["space_id"],
            normalized["year"],
            normalized["province"],
            normalized["subject_type"],
            normalized["batch"],
            normalized["major_name"],
        )
        unique[key] = normalized
    return list(unique.values())


def normalize_strong_foundation_rows(
    path: Path,
    *,
    year_filter: str,
    province_filter: str,
    subject_type_filter: str,
) -> list[dict[str, Any]]:
    if subject_type_filter or (year_filter and year_filter != "2025") or not path.exists():
        return []
    workbook = load_workbook(path, data_only=True, read_only=True)
    worksheet = workbook.active
    headers = [clean_header(cell) for cell in next(worksheet.iter_rows(min_row=1, max_row=1, values_only=True))]
    province_index = headers.index("省份")
    program_index = headers.index(clean_header("数学与应用数学\n（智能科学）\n强基计划"))
    rows: list[dict[str, Any]] = []
    for values in worksheet.iter_rows(min_row=2, values_only=True):
        province = clean(values[province_index])
        if not province or province_filter and province != province_filter:
            continue
        raw_cell = clean(values[program_index])
        min_score, min_rank = parse_score_rank_cell(raw_cell)
        if min_score is None:
            continue
        source_text = strong_foundation_row_markdown(
            {
                "year": 2025,
                "province": province,
                "program_name": STRONG_FOUNDATION_PROGRAM,
                "min_score": min_score,
                "min_rank": min_rank,
            }
        )
        rows.append(
            {
                "space_id": SPACE_ID,
                "year": 2025,
                "province": province,
                "program_name": STRONG_FOUNDATION_PROGRAM,
                "subject_type": "",
                "min_score": min_score,
                "min_rank": min_rank,
                "source_url": SOURCE_URL,
                "source_document": path.name,
                "source_text": source_text,
                "source_department": "武汉大学本科招生办公室",
                "published_at": "2025",
                "raw_json": {
                    "source_file": str(path),
                    "province": province,
                    "program_name": STRONG_FOUNDATION_PROGRAM,
                    "score_rank_cell": raw_cell,
                },
            }
        )
    workbook.close()
    return rows


def build_admission_entities(
    *,
    plans: list[dict[str, Any]],
    scores: list[dict[str, Any]],
    strong_foundation_scores: list[dict[str, Any]],
    seed_path: Path,
) -> dict[str, list[dict[str, Any]]]:
    entities: dict[str, dict[str, Any]] = {}
    aliases: dict[tuple[str, str], dict[str, Any]] = {}
    relations: dict[tuple[str, str, str], dict[str, Any]] = {}
    seed_keys: dict[str, str] = {}

    def add_entity(
        *,
        entity_type: str,
        canonical_name: str,
        description: str = "",
        source_collection: str = "",
        source_key: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        entity_id = stable_entity_id(SPACE_ID, entity_type, canonical_name)
        entities[entity_id] = {
            "entity_id": entity_id,
            "space_id": SPACE_ID,
            "entity_type": entity_type,
            "canonical_name": canonical_name,
            "description": description,
            "source_collection": source_collection,
            "source_key": source_key,
            "metadata": metadata or {},
        }
        add_alias(entity_id, canonical_name, "official", 1.0)
        return entity_id

    def add_alias(entity_id: str, alias: str, alias_type: str, confidence: float) -> None:
        normalized = normalize_entity_text(alias)
        if not normalized:
            return
        aliases[(entity_id, normalized)] = {
            "entity_id": entity_id,
            "space_id": SPACE_ID,
            "alias": alias,
            "normalized_alias": normalized,
            "alias_type": alias_type,
            "confidence": confidence,
        }

    def add_relation(subject_id: str, predicate: str, object_id: str, confidence: float) -> None:
        relations[(subject_id, predicate, object_id)] = {
            "space_id": SPACE_ID,
            "subject_entity_id": subject_id,
            "predicate": predicate,
            "object_entity_id": object_id,
            "confidence": confidence,
        }

    seed_payload = load_entity_seed(seed_path)
    for seed in seed_payload.get("entities", []):
        if not isinstance(seed, dict):
            continue
        entity_id = add_entity(
            entity_type=clean(seed.get("entity_type")),
            canonical_name=clean(seed.get("canonical_name")),
            description=clean(seed.get("description")),
            source_collection=clean(seed.get("source_collection")),
            source_key=clean(seed.get("source_key")),
            metadata=dict(seed.get("metadata") or {}) if isinstance(seed.get("metadata"), dict) else {},
        )
        if seed.get("key"):
            seed_keys[str(seed["key"])] = entity_id
        for alias_item in seed.get("aliases") or []:
            if not isinstance(alias_item, dict):
                continue
            add_alias(
                entity_id,
                clean(alias_item.get("alias")),
                clean(alias_item.get("alias_type")) or "alias",
                float(alias_item.get("confidence") or 1.0),
            )
    for relation in seed_payload.get("relations", []):
        if not isinstance(relation, dict):
            continue
        subject_id = seed_keys.get(str(relation.get("subject_key") or ""))
        object_id = seed_keys.get(str(relation.get("object_key") or ""))
        predicate = clean(relation.get("predicate"))
        if subject_id and object_id and predicate:
            add_relation(subject_id, predicate, object_id, float(relation.get("confidence") or 1.0))

    for row in plans + scores:
        major_name = clean(row.get("major_name"))
        if not major_name:
            continue
        major_id = add_entity(
            entity_type="major",
            canonical_name=major_name,
            source_collection="admissions",
            source_key=major_name,
            metadata={
                "fact_tables": ["admission_plans", "admission_scores"],
                "fact_column": "major_name",
            },
        )
        add_alias(major_id, major_name.replace("（", "(").replace("）", ")"), "display_variant", 0.96)
        for group in re_parentheses(major_name):
            add_alias(major_id, group, "short_name", 0.72)
    for province in sorted({clean(row.get("province")) for row in plans + scores + strong_foundation_scores}):
        if not province:
            continue
        province_id = add_entity(
            entity_type="province",
            canonical_name=province,
            source_collection="admissions",
            source_key=province,
            metadata={"fact_column": "province"},
        )
        add_alias(province_id, province, "official", 1.0)

    if strong_foundation_scores:
        program_id = add_entity(
            entity_type="program",
            canonical_name=STRONG_FOUNDATION_PROGRAM,
            description="武汉大学数学与应用数学（智能科学）强基计划录取分数",
            source_collection="admission_strong_foundation_scores",
            source_key=STRONG_FOUNDATION_PROGRAM,
            metadata={
                "fact_table": "admission_strong_foundation_scores",
                "fact_column": "program_name",
                "metric": "min_score",
            },
        )
        for alias, confidence in (
            ("数学与应用数学智能科学强基计划", 0.98),
            ("智能科学强基计划", 0.95),
            ("智能科学强基", 0.92),
            ("数学智能科学强基", 0.9),
        ):
            add_alias(program_id, alias, "short_name", confidence)
        if seed_keys.get("strong_foundation"):
            add_relation(program_id, "is_a", seed_keys["strong_foundation"], 1.0)
        if seed_keys.get("sai"):
            add_relation(program_id, "related_to", seed_keys["sai"], 0.85)

    return {
        "entities": list(entities.values()),
        "aliases": list(aliases.values()),
        "relations": list(relations.values()),
    }


def build_search_items(
    *,
    entity_payload: dict[str, list[dict[str, Any]]],
    plans: list[dict[str, Any]],
    scores: list[dict[str, Any]],
    strong_foundation_scores: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    aliases_by_entity: dict[str, list[dict[str, Any]]] = {}
    for alias in entity_payload["aliases"]:
        aliases_by_entity.setdefault(str(alias["entity_id"]), []).append(alias)
    for entity in entity_payload["entities"]:
        entity_aliases = sorted(
            aliases_by_entity.get(str(entity["entity_id"]), []),
            key=lambda item: float(item.get("confidence") or 0.0),
            reverse=True,
        )
        alias_text = "，".join(str(alias["alias"]) for alias in entity_aliases[:20])
        content = "\n".join(
            part
            for part in (
                str(entity["canonical_name"]),
                f"类型：{entity['entity_type']}",
                f"别名：{alias_text}" if alias_text else "",
                f"描述：{entity.get('description')}" if entity.get("description") else "",
            )
            if part
        )
        items.append(
            {
                "item_id": stable_search_item_id(SPACE_ID, "entity", str(entity["entity_id"])),
                "space_id": SPACE_ID,
                "item_type": "entity",
                "entity_id": entity["entity_id"],
                "title": str(entity["canonical_name"]),
                "content_text": content,
                "metadata": {
                    "entity_type": entity["entity_type"],
                    "canonical_name": entity["canonical_name"],
                    "description": entity.get("description") or "",
                    "entity_metadata": entity.get("metadata") or {},
                    "aliases": [alias["alias"] for alias in entity_aliases],
                },
            }
        )
    for row in plans:
        key = "|".join(
            str(row.get(field) or "")
            for field in ("year", "province", "subject_type", "batch", "major_name", "class_type")
        )
        items.append(
            {
                "item_id": stable_search_item_id(SPACE_ID, "fact", f"admission_plans:{key}"),
                "space_id": SPACE_ID,
                "item_type": "fact",
                "fact_table": "admission_plans",
                "fact_key": key,
                "title": "武汉大学本科招生计划",
                "content_text": plan_row_markdown(row),
                "metadata": row,
            }
        )
    for row in scores:
        key = "|".join(
            str(row.get(field) or "")
            for field in ("year", "province", "subject_type", "batch", "major_name")
        )
        items.append(
            {
                "item_id": stable_search_item_id(SPACE_ID, "fact", f"admission_scores:{key}"),
                "space_id": SPACE_ID,
                "item_type": "fact",
                "fact_table": "admission_scores",
                "fact_key": key,
                "title": "武汉大学历年录取分数",
                "content_text": score_row_markdown(row),
                "metadata": row,
            }
        )
    for row in strong_foundation_scores:
        key = "|".join(str(row.get(field) or "") for field in ("year", "province", "program_name"))
        items.append(
            {
                "item_id": stable_search_item_id(SPACE_ID, "fact", f"admission_strong_foundation_scores:{key}"),
                "space_id": SPACE_ID,
                "item_type": "fact",
                "fact_table": "admission_strong_foundation_scores",
                "fact_key": key,
                "title": "武汉大学强基计划录取分数",
                "content_text": strong_foundation_row_markdown(row),
                "metadata": row,
            }
        )
    return items


def load_entity_seed(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"entities": [], "relations": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {"entities": [], "relations": []}


def row_to_plan(*, normalized_source: dict[str, Any]) -> dict[str, Any]:
    return {
        "year": normalized_source.get("nf"),
        "province": normalized_source.get("sf"),
        "subject_type": normalized_source.get("klmc"),
        "batch": normalized_source.get("zslb") or normalized_source.get("pcmc"),
        "major_name": normalized_source.get("zymc"),
        "plan_count": normalized_source.get("jhrs"),
        "tuition": normalized_source.get("zyxf"),
        "schooling_years": normalized_source.get("xzmc"),
        "remarks": plan_remarks(normalized_source),
    }


def row_to_score(*, normalized_source: dict[str, Any]) -> dict[str, Any]:
    return {
        "year": normalized_source.get("nf"),
        "province": normalized_source.get("sf"),
        "subject_type": normalized_source.get("klmc"),
        "batch": normalized_source.get("zslb") or normalized_source.get("pcmc"),
        "major_name": normalized_source.get("zymc"),
        "min_score": normalized_source.get("zdf"),
        "max_score": normalized_source.get("zgf"),
        "avg_score": normalized_source.get("pjf"),
        "min_rank": normalized_source.get("zdfwc"),
    }


def write_dataset_artifact(
    artifact_store: MarkdownArtifactStore,
    *,
    title: str,
    url: str,
    rows: list[dict[str, Any]],
    raw_payload: list[dict[str, Any]],
    row_markdown,
):
    body = dataset_markdown(title=title, rows=rows, row_markdown=row_markdown)
    quality = MarkdownQualityChecker().check(body).to_dict()
    return artifact_store.write_document(
        site_id=SITE_ID,
        space_id=SPACE_ID,
        url=url,
        title=title,
        published_at=current_year(rows),
        markdown_body=body,
        raw_html=json.dumps(raw_payload, ensure_ascii=False, indent=2),
        quality=quality,
        depth=0,
        links=[{"url": SOURCE_URL, "text": "武汉大学本科招生数据查询", "is_asset": False}],
    )


async def index_artifact(store: PostgresKnowledgeStore, artifact) -> None:
    await store.upsert_document(
        IndexedDocument(
            document_id=artifact.document_id,
            space_id=str(artifact.metadata["space_id"]),
            site_id=str(artifact.metadata["site_id"]),
            title=str(artifact.metadata["title"]),
            source_url=str(artifact.metadata["url"]),
            published_at=artifact.metadata.get("published_at"),
            content_hash=str(artifact.metadata["content_hash"]),
            markdown_path=str(artifact.markdown_path),
            raw_html_path=str(artifact.raw_html_path),
            quality=dict(artifact.metadata.get("quality") or {}),
            markdown=artifact.markdown,
        )
    )


def dataset_markdown(*, title: str, rows: list[dict[str, Any]], row_markdown) -> str:
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((int(row["year"]), str(row["province"])), []).append(row)
    lines = [f"# {title}", "", f"数据来源：[{SOURCE_URL}]({SOURCE_URL})", ""]
    for (year, province), group in sorted(grouped.items(), reverse=True):
        lines.extend([f"## {year} {province}", ""])
        for row in sorted(group, key=lambda item: (str(item.get("subject_type")), str(item.get("major_name")))):
            lines.append(f"- {row_markdown(row)}")
        lines.append("")
    return "\n".join(lines).strip()


def plan_row_markdown(row: dict[str, Any]) -> str:
    parts = [
        f"{row.get('year')}年",
        str(row.get("province")),
        str(row.get("subject_type")),
        str(row.get("batch")),
        f"{row.get('major_name')} 招生计划 {row.get('plan_count')} 人",
    ]
    if row.get("schooling_years"):
        parts.append(f"学制 {row.get('schooling_years')}")
    if row.get("tuition"):
        parts.append(f"学费 {row.get('tuition')} 元/年")
    if row.get("remarks"):
        parts.append(str(row.get("remarks")))
    return "，".join(part for part in parts if part and part != "None")


def score_row_markdown(row: dict[str, Any]) -> str:
    parts = [
        f"{row.get('year')}年",
        str(row.get("province")),
        str(row.get("subject_type")),
        str(row.get("batch")),
        f"{row.get('major_name')} 最低分 {row.get('min_score')}",
        f"最高分 {row.get('max_score')}",
        f"平均分 {row.get('avg_score')}",
    ]
    if row.get("min_rank"):
        parts.append(f"最低位次 {row.get('min_rank')}")
    return "，".join(part for part in parts if part and part != "None")


def strong_foundation_row_markdown(row: dict[str, Any]) -> str:
    parts = [
        f"{row.get('year')}年",
        str(row.get("province")),
        str(row.get("program_name")),
        f"最低分 {row.get('min_score')}",
    ]
    if row.get("min_rank"):
        parts.append(f"最低位次 {row.get('min_rank')}")
    return "，".join(part for part in parts if part and part != "None")


def plan_remarks(row: dict[str, Any]) -> str:
    remarks = []
    if clean(row.get("zybz")):
        remarks.append(f"包含专业：{clean(row.get('zybz'))}")
    if clean(row.get("xkyq")):
        remarks.append(f"选考要求：{clean(row.get('xkyq'))}")
    if clean(row.get("zygroup")):
        remarks.append(f"专业组：{clean(row.get('zygroup'))}")
    return "；".join(remarks)


def current_year(rows: list[dict[str, Any]]) -> str | None:
    years = sorted({int(row["year"]) for row in rows if row.get("year")}, reverse=True)
    return str(years[0]) if years else None


def clean(value: Any) -> str:
    return str(value or "").strip()


def as_int(value: Any) -> int | None:
    text = clean(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def as_float(value: Any) -> float | None:
    text = clean(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_score_rank_cell(value: Any) -> tuple[float | None, int | None]:
    text = clean(value)
    if not text:
        return None, None
    parts = text.replace("／", "/").split("/")
    score = as_float(parts[0])
    rank = as_int(parts[1]) if len(parts) > 1 else None
    return score, rank


def clean_header(value: Any) -> str:
    return "".join(str(value or "").split())


def re_parentheses(value: str) -> list[str]:
    groups = []
    for group in re.findall(r"[（(]([^（）()]+)[）)]", value):
        text = group.strip()
        normalized = normalize_entity_text(text)
        if len(normalized) < 3 or re.fullmatch(r"\d+年?", normalized):
            continue
        groups.append(text)
    return groups


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


if __name__ == "__main__":
    asyncio.run(main())
