from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import asyncpg

from luoying_bot.capabilities.knowledge_base.embeddings import EmbeddingProvider
from luoying_bot.capabilities.knowledge_base.errors import BackendUnavailable
from luoying_bot.capabilities.knowledge_base.models import Citation, RetrievedChunk
from luoying_bot.capabilities.knowledge_base.ports import AnalyticsBackend, RagBackend, StructuredBackend


@dataclass(slots=True)
class IndexedDocument:
    document_id: str
    space_id: str
    site_id: str
    title: str
    source_url: str
    published_at: str | None
    content_hash: str
    markdown_path: str
    raw_html_path: str
    quality: dict[str, Any]
    markdown: str


class PostgresKnowledgeStore(AnalyticsBackend, RagBackend, StructuredBackend):
    def __init__(
        self,
        database_url: str,
        *,
        embedding_provider: EmbeddingProvider,
        embedding_dimensions: int,
    ):
        self.database_url = database_url
        self.embedding_provider = embedding_provider
        self.embedding_dimensions = embedding_dimensions
        self._pool: asyncpg.Pool | None = None

    async def ensure_schema(self) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("create extension if not exists vector")
            await conn.execute(
                f"""
                create table if not exists kb_documents (
                    document_id text primary key,
                    space_id text not null,
                    site_id text not null,
                    title text not null,
                    source_url text not null,
                    published_at text,
                    content_hash text not null,
                    markdown_path text not null,
                    raw_html_path text not null,
                    quality_json jsonb not null,
                    status text not null,
                    updated_at timestamptz not null default now()
                );

                create table if not exists kb_chunks (
                    chunk_id text primary key,
                    document_id text not null references kb_documents(document_id) on delete cascade,
                    chunk_index integer not null,
                    title text not null,
                    source_url text not null,
                    published_at text,
                    text text not null,
                    search_text text not null,
                    embedding vector({self.embedding_dimensions}) not null,
                    embedding_provider text not null,
                    embedding_model text not null,
                    embedding_dimensions integer not null,
                    search_vector tsvector generated always as (to_tsvector('simple', search_text)) stored
                );

                create table if not exists kb_events (
                    id bigserial primary key,
                    collection text not null,
                    payload_json jsonb not null,
                    created_at timestamptz not null default now()
                );

                create table if not exists admission_plans (
                    id bigserial primary key,
                    space_id text not null,
                    year integer not null,
                    province text not null,
                    subject_type text not null,
                    batch text not null default '',
                    major_name text not null,
                    class_type text not null default '',
                    plan_count integer,
                    tuition text,
                    schooling_years text,
                    remarks text,
                    source_url text,
                    source_document text,
                    source_text text,
                    source_department text,
                    published_at text,
                    review_status text not null default 'approved',
                    raw_json jsonb not null default '{{}}'::jsonb,
                    updated_at timestamptz not null default now(),
                    unique(space_id, year, province, subject_type, batch, major_name, class_type)
                );

                create table if not exists admission_scores (
                    id bigserial primary key,
                    space_id text not null,
                    year integer not null,
                    province text not null,
                    subject_type text not null,
                    batch text not null default '',
                    major_name text not null,
                    min_score numeric,
                    max_score numeric,
                    avg_score numeric,
                    min_rank integer,
                    source_url text,
                    source_document text,
                    source_text text,
                    source_department text,
                    published_at text,
                    review_status text not null default 'approved',
                    raw_json jsonb not null default '{{}}'::jsonb,
                    updated_at timestamptz not null default now(),
                    unique(space_id, year, province, subject_type, batch, major_name)
                );

                create table if not exists admission_strong_foundation_scores (
                    id bigserial primary key,
                    space_id text not null,
                    year integer not null,
                    province text not null,
                    program_name text not null,
                    subject_type text not null default '',
                    min_score numeric,
                    min_rank integer,
                    source_url text,
                    source_document text,
                    source_text text,
                    source_department text,
                    published_at text,
                    review_status text not null default 'approved',
                    raw_json jsonb not null default '{{}}'::jsonb,
                    updated_at timestamptz not null default now(),
                    unique(space_id, year, province, program_name)
                );

                create table if not exists majors (
                    id bigserial primary key,
                    space_id text not null,
                    name text not null,
                    school_name text,
                    degree text,
                    category text,
                    source_url text,
                    source_document text,
                    source_text text,
                    source_department text,
                    published_at text,
                    review_status text not null default 'approved',
                    raw_json jsonb not null default '{{}}'::jsonb,
                    updated_at timestamptz not null default now(),
                    unique(space_id, name)
                );

                create table if not exists class_types (
                    id bigserial primary key,
                    space_id text not null,
                    name text not null,
                    description text,
                    source_url text,
                    source_document text,
                    source_text text,
                    source_department text,
                    published_at text,
                    review_status text not null default 'approved',
                    raw_json jsonb not null default '{{}}'::jsonb,
                    updated_at timestamptz not null default now(),
                    unique(space_id, name)
                );
                """
            )
            await conn.execute(
                "create index if not exists kb_documents_space_status_idx on kb_documents(space_id, status)"
            )
            await conn.execute(
                "create index if not exists kb_chunks_document_idx on kb_chunks(document_id, chunk_index)"
            )
            await conn.execute(
                "create index if not exists kb_chunks_search_idx on kb_chunks using gin(search_vector)"
            )
            await conn.execute(
                "create index if not exists kb_chunks_embedding_idx on kb_chunks using hnsw (embedding vector_cosine_ops)"
            )
            await conn.execute(
                "create index if not exists admission_plans_lookup_idx on admission_plans(space_id, year, province, subject_type)"
            )
            await conn.execute(
                "create index if not exists admission_scores_lookup_idx on admission_scores(space_id, year, province, subject_type)"
            )
            await conn.execute(
                "create index if not exists admission_strong_foundation_lookup_idx on admission_strong_foundation_scores(space_id, year, province)"
            )

    async def upsert_document(self, document: IndexedDocument) -> None:
        chunks = chunk_markdown(document.markdown)
        embeddings = await self.embedding_provider.embed_texts(
            [embedding_input(document.title, text) for text in chunks]
        )
        self._validate_embeddings(embeddings)
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    insert into kb_documents (
                        document_id, space_id, site_id, title, source_url, published_at,
                        content_hash, markdown_path, raw_html_path, quality_json, status, updated_at
                    )
                    values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, 'active', now())
                    on conflict(document_id) do update set
                        space_id=excluded.space_id,
                        site_id=excluded.site_id,
                        title=excluded.title,
                        source_url=excluded.source_url,
                        published_at=excluded.published_at,
                        content_hash=excluded.content_hash,
                        markdown_path=excluded.markdown_path,
                        raw_html_path=excluded.raw_html_path,
                        quality_json=excluded.quality_json,
                        status='active',
                        updated_at=now()
                    """,
                    document.document_id,
                    document.space_id,
                    document.site_id,
                    document.title,
                    document.source_url,
                    document.published_at,
                    document.content_hash,
                    document.markdown_path,
                    document.raw_html_path,
                    json.dumps(document.quality, ensure_ascii=False),
                )
                await conn.execute("delete from kb_chunks where document_id = $1", document.document_id)
                for index, text in enumerate(chunks):
                    embedding = embeddings[index]
                    await conn.execute(
                        """
                        insert into kb_chunks (
                            chunk_id, document_id, chunk_index, title, source_url,
                            published_at, text, search_text, embedding, embedding_provider,
                            embedding_model, embedding_dimensions
                        )
                        values ($1, $2, $3, $4, $5, $6, $7, $8, $9::vector, $10, $11, $12)
                        """,
                        f"{document.document_id}:{index}",
                        document.document_id,
                        index,
                        document.title,
                        document.source_url,
                        document.published_at,
                        text,
                        searchable_text(f"{document.title}\n{text}"),
                        vector_literal(embedding),
                        self.embedding_provider.provider_id,
                        self.embedding_provider.model,
                        len(embedding),
                    )

    async def replace_site_documents(self, *, site_id: str, active_document_ids: list[str]) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if active_document_ids:
                rows = await conn.fetch(
                    """
                    select document_id
                    from kb_documents
                    where site_id = $1 and not (document_id = any($2::text[]))
                    """,
                    site_id,
                    active_document_ids,
                )
            else:
                rows = await conn.fetch(
                    "select document_id from kb_documents where site_id = $1",
                    site_id,
                )
            stale_ids = [str(row["document_id"]) for row in rows]
            if not stale_ids:
                return
            await conn.execute(
                """
                update kb_documents
                set status = 'inactive', updated_at = now()
                where document_id = any($1::text[])
                """,
                stale_ids,
            )
            await conn.execute("delete from kb_chunks where document_id = any($1::text[])", stale_ids)

    async def search(
        self,
        *,
        query: str,
        dataset_id: str,
        filters: dict[str, Any],
        top_k: int,
    ) -> list[RetrievedChunk]:
        del dataset_id
        space_id = str(filters.get("space_id") or "")
        query_vector = (await self.embedding_provider.embed_texts([query]))[0]
        self._validate_embeddings([query_vector])
        query_terms = extract_keyword_terms(query)
        candidate_limit = max(50, top_k * 12)
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            title = await self._title_candidates(
                conn,
                query=query,
                query_terms=query_terms,
                space_id=space_id,
                limit=candidate_limit,
            )
            lexical = await self._lexical_candidates(
                conn,
                query=query,
                space_id=space_id,
                limit=candidate_limit,
            )
            vector = await self._vector_candidates(
                conn,
                query_vector=query_vector,
                space_id=space_id,
                limit=candidate_limit,
            )

        combined: dict[str, dict[str, Any]] = {}
        for row in title:
            combined.setdefault(row["chunk_id"], row)["title_score"] = row["title_score"]
        for row in lexical:
            combined.setdefault(row["chunk_id"], row)["lexical_score"] = row["lexical_score"]
        for row in vector:
            item = combined.setdefault(row["chunk_id"], row)
            item["vector_score"] = row["vector_score"]
        scored = []
        for item in combined.values():
            title_score = float(item.get("title_score") or 0.0)
            lexical_score = float(item.get("lexical_score") or 0.0)
            vector_score = float(item.get("vector_score") or 0.0)
            phrase_score = phrase_overlap_score(
                query_terms=query_terms,
                title=str(item.get("title") or ""),
                text=str(item.get("text") or ""),
            )
            item["phrase_score"] = phrase_score
            item["score"] = (
                2.8 * title_score
                + 1.4 * phrase_score
                + 1.0 * vector_score
                + 0.7 * lexical_score
            )
            scored.append(item)
        apply_document_support(scored)
        scored.sort(key=lambda item: item["score"], reverse=True)
        chunks: list[RetrievedChunk] = []
        for item in scored[:top_k]:
            citation = Citation(
                title=str(item["title"]),
                source=str(item["source_url"]),
                snippet=str(item["text"])[:500],
                published_at=item.get("published_at"),
                metadata={
                    "document_id": item["document_id"],
                    "chunk_id": item["chunk_id"],
                    "score": item["score"],
                    "title_score": item.get("title_score", 0.0),
                    "lexical_score": item.get("lexical_score", 0.0),
                    "vector_score": item.get("vector_score", 0.0),
                    "phrase_score": item.get("phrase_score", 0.0),
                    "document_support_score": item.get("document_support_score", 0.0),
                    "embedding_model": item.get("embedding_model"),
                },
            )
            chunks.append(
                RetrievedChunk(
                    text=str(item["text"]),
                    score=float(item["score"]),
                    citation=citation,
                    metadata=dict(item),
                )
            )
        return chunks

    async def list_items(
        self,
        collection: str,
        *,
        filters: dict[str, Any],
        fields: list[str] | None = None,
        limit: int = 20,
        sort: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if collection in {"kb_pages", "kb_documents"}:
            rows = await self._list_documents(filters=filters, limit=limit, sort=sort)
        elif collection in {
            "admission_plans",
            "admission_scores",
            "admission_strong_foundation_scores",
            "majors",
            "class_types",
        }:
            rows = await self._list_structured(collection, filters=filters, limit=limit, sort=sort)
        else:
            rows = []
        return [project_fields(row, fields) for row in rows]

    async def create_item(self, collection: str, payload: dict[str, Any]) -> dict[str, Any]:
        if collection not in {"kb_answer_logs", "kb_feedback", "dynamic_qa", "kb_crawl_runs"}:
            raise BackendUnavailable(f"Postgres 知识库不支持写入集合：{collection}")
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                insert into kb_events (collection, payload_json)
                values ($1, $2::jsonb)
                returning id
                """,
                collection,
                json.dumps(jsonable(payload), ensure_ascii=False),
            )
        return {"id": str(row["id"]), **payload}

    async def update_item(self, collection: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if collection != "kb_crawl_runs":
            raise BackendUnavailable(f"Postgres 知识库不支持更新集合：{collection}")
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("select payload_json from kb_events where id = $1", int(item_id))
            if row is None:
                raise BackendUnavailable(f"Postgres 记录不存在：{collection}/{item_id}")
            data = dict(row["payload_json"])
            data.update(payload)
            await conn.execute(
                "update kb_events set payload_json = $1::jsonb where id = $2",
                json.dumps(jsonable(data), ensure_ascii=False),
                int(item_id),
            )
        return {"id": item_id, **data}

    async def distinct_values(
        self,
        collection: str,
        field: str,
        *,
        filters: dict[str, Any] | None = None,
        limit: int = 10000,
    ) -> list[str]:
        if collection not in STRUCTURED_FILTER_FIELDS or field not in STRUCTURED_FILTER_FIELDS[collection]:
            raise BackendUnavailable(f"Postgres 知识库不支持实体字段：{collection}.{field}")
        normalized = normalize_filter(filters or {})
        allowed_fields = STRUCTURED_FILTER_FIELDS[collection]
        clauses = [f"{field} is not null", f"{field} <> ''"]
        values: list[Any] = []
        for key, value in normalized.items():
            if key == field or key == "id_in" or key not in allowed_fields:
                continue
            if value in (None, ""):
                continue
            values.append(value)
            clauses.append(f"{key} = ${len(values)}")
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                select distinct {field} as value
                from {collection}
                where {" and ".join(clauses)}
                order by value
                limit ${len(values) + 1}
                """,
                *values,
                limit,
            )
        return [str(row["value"]) for row in rows if str(row["value"]).strip()]

    async def execute_select(self, sql: str, *, limit: int) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql)
        return [record_to_dict(row) for row in rows[:limit]]

    async def upsert_admission_plans(self, rows: list[dict[str, Any]]) -> int:
        pool = await self._get_pool()
        count = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                for item in rows:
                    await conn.execute(
                        """
                        insert into admission_plans (
                            space_id, year, province, subject_type, batch, major_name,
                            class_type, plan_count, tuition, schooling_years, remarks,
                            source_url, source_document, source_text, source_department,
                            published_at, review_status, raw_json, updated_at
                        )
                        values (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                            $12, $13, $14, $15, $16, 'approved', $17::jsonb, now()
                        )
                        on conflict(space_id, year, province, subject_type, batch, major_name, class_type)
                        do update set
                            plan_count=excluded.plan_count,
                            tuition=excluded.tuition,
                            schooling_years=excluded.schooling_years,
                            remarks=excluded.remarks,
                            source_url=excluded.source_url,
                            source_document=excluded.source_document,
                            source_text=excluded.source_text,
                            source_department=excluded.source_department,
                            published_at=excluded.published_at,
                            review_status='approved',
                            raw_json=excluded.raw_json,
                            updated_at=now()
                        """,
                        item["space_id"],
                        int(item["year"]),
                        item["province"],
                        item["subject_type"],
                        item.get("batch") or "",
                        item["major_name"],
                        item.get("class_type") or "",
                        item.get("plan_count"),
                        item.get("tuition"),
                        item.get("schooling_years"),
                        item.get("remarks"),
                        item.get("source_url"),
                        item.get("source_document"),
                        item.get("source_text"),
                        item.get("source_department"),
                        item.get("published_at"),
                        json.dumps(item.get("raw_json") or {}, ensure_ascii=False),
                    )
                    count += 1
        return count

    async def upsert_admission_scores(self, rows: list[dict[str, Any]]) -> int:
        pool = await self._get_pool()
        count = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                for item in rows:
                    await conn.execute(
                        """
                        insert into admission_scores (
                            space_id, year, province, subject_type, batch, major_name,
                            min_score, max_score, avg_score, min_rank,
                            source_url, source_document, source_text, source_department,
                            published_at, review_status, raw_json, updated_at
                        )
                        values (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                            $11, $12, $13, $14, $15, 'approved', $16::jsonb, now()
                        )
                        on conflict(space_id, year, province, subject_type, batch, major_name)
                        do update set
                            min_score=excluded.min_score,
                            max_score=excluded.max_score,
                            avg_score=excluded.avg_score,
                            min_rank=excluded.min_rank,
                            source_url=excluded.source_url,
                            source_document=excluded.source_document,
                            source_text=excluded.source_text,
                            source_department=excluded.source_department,
                            published_at=excluded.published_at,
                            review_status='approved',
                            raw_json=excluded.raw_json,
                            updated_at=now()
                        """,
                        item["space_id"],
                        int(item["year"]),
                        item["province"],
                        item["subject_type"],
                        item.get("batch") or "",
                        item["major_name"],
                        item.get("min_score"),
                        item.get("max_score"),
                        item.get("avg_score"),
                        item.get("min_rank"),
                        item.get("source_url"),
                        item.get("source_document"),
                        item.get("source_text"),
                        item.get("source_department"),
                        item.get("published_at"),
                        json.dumps(item.get("raw_json") or {}, ensure_ascii=False),
                    )
                    count += 1
        return count

    async def upsert_admission_strong_foundation_scores(self, rows: list[dict[str, Any]]) -> int:
        pool = await self._get_pool()
        count = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                for item in rows:
                    await conn.execute(
                        """
                        insert into admission_strong_foundation_scores (
                            space_id, year, province, program_name, subject_type,
                            min_score, min_rank, source_url, source_document, source_text,
                            source_department, published_at, review_status, raw_json, updated_at
                        )
                        values (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                            $11, $12, 'approved', $13::jsonb, now()
                        )
                        on conflict(space_id, year, province, program_name)
                        do update set
                            subject_type=excluded.subject_type,
                            min_score=excluded.min_score,
                            min_rank=excluded.min_rank,
                            source_url=excluded.source_url,
                            source_document=excluded.source_document,
                            source_text=excluded.source_text,
                            source_department=excluded.source_department,
                            published_at=excluded.published_at,
                            review_status='approved',
                            raw_json=excluded.raw_json,
                            updated_at=now()
                        """,
                        item["space_id"],
                        int(item["year"]),
                        item["province"],
                        item["program_name"],
                        item.get("subject_type") or "",
                        item.get("min_score"),
                        item.get("min_rank"),
                        item.get("source_url"),
                        item.get("source_document"),
                        item.get("source_text"),
                        item.get("source_department"),
                        item.get("published_at"),
                        json.dumps(item.get("raw_json") or {}, ensure_ascii=False),
                    )
                    count += 1
        return count

    async def _list_documents(self, *, filters: dict[str, Any], limit: int, sort: list[str] | None) -> list[dict[str, Any]]:
        del sort
        normalized = normalize_filter(filters)
        where, values = build_where(
            {
                "status": "active",
                **({"space_id": normalized["space_id"]} if normalized.get("space_id") else {}),
            },
            start_index=1,
        )
        extra = ""
        if normalized.get("id_in"):
            extra = f" and document_id = any(${len(values) + 1}::text[])"
            values.append(normalized["id_in"])
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                select document_id as id, document_id, site_id, space_id, source_url as canonical_url,
                       title, published_at, content_hash, status, markdown_path, quality_json
                from kb_documents
                where {where}{extra}
                order by title
                limit ${len(values) + 1}
                """,
                *values,
                limit,
            )
        return [record_to_dict(row) for row in rows]

    async def _list_structured(
        self,
        collection: str,
        *,
        filters: dict[str, Any],
        limit: int,
        sort: list[str] | None,
    ) -> list[dict[str, Any]]:
        normalized = normalize_filter(filters)
        allowed_fields = STRUCTURED_FILTER_FIELDS[collection]
        clauses = []
        values: list[Any] = []
        for field, value in normalized.items():
            if field == "id_in" or field not in allowed_fields or value in (None, ""):
                continue
            values.append(value)
            clauses.append(f"{field} = ${len(values)}")
        where = " and ".join(clauses) if clauses else "true"
        order_by = "year desc, id asc" if sort and "-year" in sort else "id asc"
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"select * from {collection} where {where} order by {order_by} limit ${len(values) + 1}",
                *values,
                limit,
            )
        return [record_to_dict(row) for row in rows]

    async def _title_candidates(
        self,
        conn: asyncpg.Connection,
        *,
        query: str,
        query_terms: list[str],
        space_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        query_compact = compact_text(query)
        if not query_compact:
            return []
        rows = await conn.fetch(
            """
            select c.chunk_id, c.document_id, c.title, c.source_url, c.published_at, c.text,
                   c.embedding_model
            from kb_chunks c
            join kb_documents d on d.document_id = c.document_id
            where c.chunk_index = 0 and d.status = 'active' and ($1 = '' or d.space_id = $1)
            """,
            space_id,
        )
        candidates: list[dict[str, Any]] = []
        for row in rows:
            item = record_to_dict(row)
            title = compact_text(str(item["title"]))
            if not title:
                continue
            overlap = title_overlap_score(query_compact=query_compact, query_terms=query_terms, title=title)
            if title in query_compact:
                item["title_score"] = min(2.0, 0.8 + len(title) / 10)
                candidates.append(item)
            elif overlap > 0:
                item["title_score"] = overlap
                candidates.append(item)
        candidates.sort(key=lambda item: item["title_score"], reverse=True)
        return candidates[:limit]

    async def _lexical_candidates(
        self,
        conn: asyncpg.Connection,
        *,
        query: str,
        space_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        ts_query = build_tsquery(query)
        if not ts_query:
            return []
        rows = await conn.fetch(
            """
            select c.chunk_id, c.document_id, c.title, c.source_url, c.published_at, c.text,
                   ts_rank_cd(c.search_vector, to_tsquery('simple', $1)) as lexical_score,
                   c.embedding_model
            from kb_chunks c
            join kb_documents d on d.document_id = c.document_id
            where c.search_vector @@ to_tsquery('simple', $1)
              and d.status = 'active'
              and ($2 = '' or d.space_id = $2)
            order by lexical_score desc
            limit $3
            """,
            ts_query,
            space_id,
            limit,
        )
        items = [record_to_dict(row) for row in rows]
        for item in items:
            item["lexical_score"] = min(4.0, float(item.get("lexical_score") or 0.0))
        return items

    async def _vector_candidates(
        self,
        conn: asyncpg.Connection,
        *,
        query_vector: list[float],
        space_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = await conn.fetch(
            """
            select c.chunk_id, c.document_id, c.title, c.source_url, c.published_at, c.text,
                   c.embedding_model,
                   1 - (c.embedding <=> $1::vector) as vector_score
            from kb_chunks c
            join kb_documents d on d.document_id = c.document_id
            where d.status = 'active' and ($2 = '' or d.space_id = $2)
            order by c.embedding <=> $1::vector
            limit $3
            """,
            vector_literal(query_vector),
            space_id,
            limit,
        )
        return [record_to_dict(row) for row in rows]

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self.database_url, min_size=1, max_size=10)
        return self._pool

    def _validate_embeddings(self, embeddings: list[list[float]]) -> None:
        for embedding in embeddings:
            if len(embedding) != self.embedding_dimensions:
                raise BackendUnavailable(
                    f"embedding dimensions mismatch: expected {self.embedding_dimensions}, got {len(embedding)}"
                )


STRUCTURED_FILTER_FIELDS: dict[str, set[str]] = {
    "admission_plans": {
        "space_id",
        "year",
        "province",
        "subject_type",
        "batch",
        "major_name",
        "class_type",
        "review_status",
    },
    "admission_scores": {
        "space_id",
        "year",
        "province",
        "subject_type",
        "batch",
        "major_name",
        "review_status",
    },
    "admission_strong_foundation_scores": {
        "space_id",
        "year",
        "province",
        "program_name",
        "subject_type",
        "review_status",
    },
    "majors": {"space_id", "name", "review_status"},
    "class_types": {"space_id", "name", "review_status"},
}


def chunk_markdown(markdown: str, *, target_chars: int = 1200, overlap_chars: int = 160) -> list[str]:
    sections = split_markdown_sections(markdown)
    chunks: list[str] = []
    current = ""
    for section in sections:
        if len(current) + len(section) + 2 <= target_chars:
            current = f"{current}\n\n{section}".strip()
            continue
        if current:
            chunks.append(current)
        while len(section) > target_chars:
            chunks.append(section[:target_chars].strip())
            section = section[target_chars - overlap_chars :].strip()
        current = section
    if current:
        chunks.append(current)
    return chunks or [markdown.strip()]


def split_markdown_sections(markdown: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("#") and current:
            parts.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        parts.append("\n".join(current).strip())
    return [part for part in parts if part]


def embedding_input(title: str, text: str) -> str:
    return f"{title.strip()}\n\n{text.strip()}".strip()


def build_tsquery(query: str) -> str:
    terms = [
        compact_text(term)
        for term in extract_keyword_terms(query)
        if compact_text(term) and "'" not in term
    ]
    return " | ".join(f"{term}:*" for term in terms[:24])


def extract_keyword_terms(query: str) -> list[str]:
    compact = compact_text(query)
    terms = re.findall(r"[A-Za-z0-9]{2,}", query.lower())
    terms.extend(chinese_ngrams(compact, min_n=2, max_n=4, limit=64))
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        if term and term not in seen:
            seen.add(term)
            result.append(term)
    return result


def compact_text(text: str) -> str:
    return "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", text.lower()))


def searchable_text(text: str) -> str:
    compact = compact_text(text)
    return " ".join(
        [
            text,
            " ".join(chinese_ngrams(compact, min_n=2, max_n=4, limit=600)),
        ]
    )


def chinese_ngrams(text: str, *, min_n: int, max_n: int, limit: int) -> list[str]:
    chinese_runs = re.findall(r"[\u4e00-\u9fff]+", text)
    grams: list[str] = []
    for run in chinese_runs:
        for size in range(min_n, max_n + 1):
            if len(run) < size:
                continue
            for index in range(0, len(run) - size + 1):
                grams.append(run[index : index + size])
                if len(grams) >= limit:
                    return grams
    return grams


def title_overlap_score(*, query_compact: str, query_terms: list[str], title: str) -> float:
    compact_terms = [compact_text(term) for term in query_terms if len(compact_text(term)) >= 2]
    matches = [term for term in compact_terms if term in title or title in term]
    if not matches:
        return 0.0
    coverage = sum(min(len(term), len(title)) for term in matches) / max(len(title), 1)
    return min(2.0, 0.35 + coverage)


def phrase_overlap_score(*, query_terms: list[str], title: str, text: str) -> float:
    title_compact = compact_text(title)
    text_compact = compact_text(text)
    score = 0.0
    seen: set[str] = set()
    for term in query_terms:
        compact = compact_text(term)
        if len(compact) < 2 or compact in seen:
            continue
        seen.add(compact)
        if compact in title_compact:
            score += 0.32
        elif compact in text_compact:
            score += 0.12
    return min(2.5, score)


def apply_document_support(items: list[dict[str, Any]]) -> None:
    by_document: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_document.setdefault(str(item.get("document_id") or ""), []).append(item)
    for document_items in by_document.values():
        if len(document_items) <= 1:
            continue
        ranked = sorted((float(item.get("score") or 0.0) for item in document_items), reverse=True)
        support = min(1.0, sum(ranked[:4]) / 30.0)
        for item in document_items:
            item["document_support_score"] = support
            item["score"] = float(item["score"]) + support


def normalize_filter(filters: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    clauses = filters.get("_and") if isinstance(filters.get("_and"), list) else []
    for clause in clauses:
        if not isinstance(clause, dict):
            continue
        for key, value in clause.items():
            if isinstance(value, dict) and "_eq" in value:
                normalized[key] = value["_eq"]
            elif isinstance(value, dict) and "_in" in value:
                normalized[f"{key}_in"] = [str(item) for item in value["_in"]]
    for key, value in filters.items():
        if isinstance(value, dict):
            if "_eq" in value:
                normalized[key] = value["_eq"]
            elif "_in" in value:
                normalized[f"{key}_in"] = [str(item) for item in value["_in"]]
        elif key != "_and":
            normalized[key] = value
    if "id_in" not in normalized and "id" in filters and isinstance(filters["id"], dict) and "_in" in filters["id"]:
        normalized["id_in"] = [str(item) for item in filters["id"]["_in"]]
    return normalized


def build_where(equals: dict[str, Any], *, start_index: int) -> tuple[str, list[Any]]:
    clauses = []
    values: list[Any] = []
    for offset, (key, value) in enumerate(equals.items(), start=start_index):
        clauses.append(f"{key} = ${offset}")
        values.append(value)
    return " and ".join(clauses) if clauses else "true", values


def project_fields(row: dict[str, Any], fields: list[str] | None) -> dict[str, Any]:
    if not fields:
        return row
    return {field: row.get(field) for field in fields if field in row}


def record_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    data = dict(row)
    for key, value in list(data.items()):
        if isinstance(value, asyncpg.pgproto.pgproto.UUID):
            data[key] = str(value)
        elif isinstance(value, (datetime, date)):
            data[key] = value.isoformat()
        elif isinstance(value, Decimal):
            data[key] = float(value)
    return data


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value
