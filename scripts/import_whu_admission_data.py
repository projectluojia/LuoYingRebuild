from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import httpx
from openpyxl import load_workbook

from luoying_bot.capabilities.knowledge_base.artifacts import MarkdownArtifactStore
from luoying_bot.capabilities.knowledge_base.embeddings import OpenAICompatibleEmbeddingProvider
from luoying_bot.capabilities.knowledge_base.postgres_store import IndexedDocument, PostgresKnowledgeStore
from luoying_bot.capabilities.knowledge_base.quality import MarkdownQualityChecker
from luoying_bot.config import settings


BASE_URL = "https://zsdata.whu.edu.cn/wzgl/wxmini"
SOURCE_URL = "https://zsdata.whu.edu.cn/public/wzgl/#/jhcx"
SITE_ID = "whu_admissions"
SPACE_ID = "whu"
STRONG_FOUNDATION_XLSX = Path("docs/2025分省（区）录取分数及位次 - 挂网 - 最新.xlsx")
STRONG_FOUNDATION_PROGRAM = "数学与应用数学（智能科学）强基计划"


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


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


if __name__ == "__main__":
    asyncio.run(main())
