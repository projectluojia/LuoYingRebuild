from __future__ import annotations

import contextlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast
from urllib.parse import urlparse

import asyncpg

from luoying_bot.capabilities.knowledge_base.embeddings import EmbeddingProvider
from luoying_bot.capabilities.knowledge_base.entities import EntityMatch, GLOBAL_ENTITY_SPACE_ID, normalize_entity_text
from luoying_bot.capabilities.knowledge_base.errors import BackendUnavailable
from luoying_bot.capabilities.knowledge_base.models import Citation, RetrievedChunk
from luoying_bot.capabilities.knowledge_base.ports import AnalyticsBackend, EntityBackend, RagBackend, StructuredBackend
from luoying_bot.capabilities.knowledge_base.rerankers import RerankCandidate, RerankedCandidate, Reranker
from luoying_bot.capabilities.knowledge_base.semantic_layer import KnowledgeSemanticLayer
from luoying_bot.capabilities.knowledge_base.text_utils import normalize_alnum_text as compact_text


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
    alias_text: str = ""


@dataclass(slots=True)
class IndexedDocumentLink:
    site_id: str
    from_document_id: str
    to_document_id: str
    from_url: str
    to_url: str
    link_text: str
    link_type: str = "content_link"
    metadata: dict[str, Any] | None = None


TITLE_RRF_WEIGHT = 1.6
ENTITY_RRF_WEIGHT = 1.45
VECTOR_RRF_WEIGHT = 1.0
BM25_RRF_WEIGHT = 1.25
DOCUMENT_DEDUP_RERANK_MULTIPLIER = 3
CONTEXT_NEIGHBOR_RADIUS = 1
CONTEXT_LINK_LIMIT = 4
CONTEXT_MAX_CHARS = 4500
PAGE_CONTEXT_MAX_CHARS = 7000


class PostgresKnowledgeStore(AnalyticsBackend, EntityBackend, RagBackend, StructuredBackend):
    def __init__(
        self,
        database_url: str,
        *,
        embedding_provider: EmbeddingProvider,
        reranker: Reranker,
        embedding_dimensions: int,
        min_rerank_score: float,
    ):
        self.database_url = database_url
        self.embedding_provider = embedding_provider
        self.reranker = reranker
        self.embedding_dimensions = embedding_dimensions
        self.min_rerank_score = min_rerank_score
        self._pool: asyncpg.Pool | None = None

    async def ensure_schema(self) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("create extension if not exists vector")
            with contextlib.suppress(asyncpg.exceptions.FeatureNotSupportedError):
                await conn.execute("create extension if not exists pg_search")
            await self._reset_vector_tables_if_embedding_dimensions_changed(conn)
            await conn.execute(
                f"""
                create table if not exists kb_documents (
                    document_id text primary key,
                    space_id text not null,
                    site_id text not null,
                    title text not null,
                    source_url text not null,
                    alias_text text not null default '',
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
                    space_id text not null,
                    chunk_index integer not null,
                    title text not null,
                    source_url text not null,
                    alias_text text not null default '',
                    published_at text,
                    text text not null,
                    search_text text not null,
                    embedding vector({self.embedding_dimensions}) not null,
                    embedding_provider text not null,
                    embedding_model text not null,
                    embedding_dimensions integer not null
                );

                create table if not exists kb_events (
                    id bigserial primary key,
                    collection text not null,
                    payload_json jsonb not null,
                    created_at timestamptz not null default now()
                );

                create table if not exists kb_document_links (
                    site_id text not null,
                    from_document_id text not null,
                    to_document_id text not null,
                    from_url text not null default '',
                    to_url text not null default '',
                    link_text text not null default '',
                    link_type text not null default 'content_link',
                    metadata_json jsonb not null default '{{}}'::jsonb,
                    updated_at timestamptz not null default now(),
                    primary key(site_id, from_document_id, to_document_id, link_text)
                );

                create table if not exists kb_entities (
                    entity_id text primary key,
                    space_id text not null,
                    entity_type text not null,
                    canonical_name text not null,
                    description text not null default '',
                    source_collection text not null default '',
                    source_key text not null default '',
                    metadata_json jsonb not null default '{{}}'::jsonb,
                    review_status text not null default 'approved',
                    updated_at timestamptz not null default now(),
                    unique(space_id, entity_type, canonical_name)
                );

                create table if not exists kb_entity_aliases (
                    id bigserial primary key,
                    entity_id text not null references kb_entities(entity_id) on delete cascade,
                    space_id text not null,
                    alias text not null,
                    normalized_alias text not null,
                    alias_type text not null default 'alias',
                    confidence numeric not null default 1,
                    review_status text not null default 'approved',
                    updated_at timestamptz not null default now(),
                    unique(space_id, entity_id, normalized_alias)
                );

                create table if not exists kb_entity_relations (
                    id bigserial primary key,
                    space_id text not null,
                    subject_entity_id text not null references kb_entities(entity_id) on delete cascade,
                    predicate text not null,
                    object_entity_id text not null references kb_entities(entity_id) on delete cascade,
                    confidence numeric not null default 1,
                    metadata_json jsonb not null default '{{}}'::jsonb,
                    review_status text not null default 'approved',
                    updated_at timestamptz not null default now(),
                    unique(space_id, subject_entity_id, predicate, object_entity_id)
                );

                create table if not exists kb_search_items (
                    item_id text primary key,
                    space_id text not null,
                    item_type text not null,
                    entity_id text references kb_entities(entity_id) on delete cascade,
                    fact_table text not null default '',
                    fact_key text not null default '',
                    document_id text,
                    chunk_id text,
                    title text not null,
                    content_text text not null,
                    search_text text not null,
                    metadata_json jsonb not null default '{{}}'::jsonb,
                    embedding vector({self.embedding_dimensions}) not null,
                    embedding_provider text not null,
                    embedding_model text not null,
                    embedding_dimensions integer not null,
                    review_status text not null default 'approved',
                    updated_at timestamptz not null default now()
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

                create table if not exists admission_content_categories (
                    category_id text primary key,
                    space_id text not null,
                    name text not null,
                    sort_order integer,
                    source_url text,
                    source_document text,
                    source_department text,
                    published_at text,
                    review_status text not null default 'approved',
                    raw_json jsonb not null default '{{}}'::jsonb,
                    updated_at timestamptz not null default now(),
                    unique(space_id, name)
                );

                create table if not exists admission_articles (
                    article_id text primary key,
                    space_id text not null,
                    category_id text references admission_content_categories(category_id) on delete set null,
                    category_name text not null default '',
                    title text not null,
                    description text not null default '',
                    source_url text,
                    logo_url text,
                    content_type text not null default '',
                    published_at text,
                    view_count integer,
                    source_document text,
                    source_department text,
                    source_text text,
                    review_status text not null default 'approved',
                    raw_json jsonb not null default '{{}}'::jsonb,
                    updated_at timestamptz not null default now()
                );

                create table if not exists academic_units (
                    unit_id text primary key,
                    space_id text not null,
                    name text not null,
                    sort_order integer,
                    source_url text,
                    source_document text,
                    source_department text,
                    published_at text,
                    review_status text not null default 'approved',
                    raw_json jsonb not null default '{{}}'::jsonb,
                    updated_at timestamptz not null default now(),
                    unique(space_id, name)
                );

                create table if not exists admission_schools (
                    school_id text primary key,
                    space_id text not null,
                    unit_id text references academic_units(unit_id) on delete set null,
                    unit_name text not null default '',
                    name text not null,
                    official_url text not null default '',
                    logo_url text not null default '',
                    sort_order integer,
                    source_url text,
                    source_document text,
                    source_department text,
                    published_at text,
                    review_status text not null default 'approved',
                    raw_json jsonb not null default '{{}}'::jsonb,
                    updated_at timestamptz not null default now(),
                    unique(space_id, name)
                );

                create table if not exists admission_media_items (
                    item_id text primary key,
                    space_id text not null,
                    category_id text not null default '',
                    category_name text not null default '',
                    title text not null,
                    item_type text not null default '',
                    source_url text,
                    media_url text not null default '',
                    logo_url text not null default '',
                    description text not null default '',
                    published_at text,
                    source_document text,
                    source_department text,
                    source_text text,
                    review_status text not null default 'approved',
                    raw_json jsonb not null default '{{}}'::jsonb,
                    updated_at timestamptz not null default now()
                );
                """
            )
            await conn.execute("drop index if exists kb_chunks_bm25_idx")
            await conn.execute("alter table kb_chunks add column if not exists space_id text")
            await conn.execute("alter table kb_documents add column if not exists alias_text text not null default ''")
            await conn.execute("alter table kb_chunks add column if not exists alias_text text not null default ''")
            await conn.execute(
                """
                update kb_chunks c
                set space_id = d.space_id
                from kb_documents d
                where d.document_id = c.document_id
                  and (c.space_id is null or c.space_id = '')
                """
            )
            await conn.execute("alter table kb_chunks alter column space_id set not null")
            await conn.execute(
                "create index if not exists kb_documents_space_status_idx on kb_documents(space_id, status)"
            )
            await conn.execute(
                "create index if not exists kb_chunks_document_idx on kb_chunks(document_id, chunk_index)"
            )
            await conn.execute(
                "create index if not exists kb_chunks_embedding_idx on kb_chunks using hnsw (embedding vector_cosine_ops)"
            )
            with contextlib.suppress(asyncpg.exceptions.FeatureNotSupportedError, asyncpg.exceptions.InvalidSchemaNameError, asyncpg.exceptions.UndefinedFunctionError):
                await conn.execute(
                    """
                    create index if not exists kb_chunks_bm25_idx on kb_chunks
                    using bm25 (
                        chunk_id,
                        space_id,
                        document_id,
                        (title::pdb.ngram(2,4)),
                        (alias_text::pdb.ngram(2,4)),
                        (search_text::pdb.ngram(2,4)),
                        source_url,
                        published_at
                    )
                    with (key_field='chunk_id')
                    """
                )
            await conn.execute(
                "create index if not exists kb_document_links_from_idx on kb_document_links(site_id, from_document_id)"
            )
            await conn.execute(
                "create index if not exists kb_document_links_to_idx on kb_document_links(site_id, to_document_id)"
            )
            await conn.execute(
                "create index if not exists kb_entities_lookup_idx on kb_entities(space_id, entity_type, review_status)"
            )
            await conn.execute(
                "create index if not exists kb_entity_aliases_lookup_idx on kb_entity_aliases(space_id, normalized_alias, review_status)"
            )
            await conn.execute(
                "create index if not exists kb_entity_relations_lookup_idx on kb_entity_relations(space_id, subject_entity_id, predicate, review_status)"
            )
            await conn.execute(
                "create index if not exists kb_search_items_lookup_idx on kb_search_items(space_id, item_type, review_status)"
            )
            await conn.execute(
                "create index if not exists kb_search_items_embedding_idx on kb_search_items using hnsw (embedding vector_cosine_ops)"
            )
            await conn.execute(
                """
                create index if not exists kb_search_items_bm25_idx on kb_search_items
                using bm25 (
                    item_id,
                    space_id,
                    item_type,
                    review_status,
                    (title::pdb.ngram(2,4)),
                    (content_text::pdb.ngram(2,4))
                )
                with (key_field='item_id')
                """
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
            await conn.execute(
                "create index if not exists admission_articles_lookup_idx on admission_articles(space_id, category_name, review_status)"
            )
            await conn.execute(
                "create index if not exists admission_schools_lookup_idx on admission_schools(space_id, unit_name, review_status)"
            )
            await conn.execute(
                "create index if not exists admission_media_items_lookup_idx on admission_media_items(space_id, category_name, review_status)"
            )

    async def close(self) -> None:
        if self._pool is None:
            return
        await self._pool.close()
        self._pool = None

    async def _reset_vector_tables_if_embedding_dimensions_changed(self, conn: asyncpg.Connection) -> None:
        for table in ("kb_chunks", "kb_search_items"):
            row = await conn.fetchrow(
                """
                select format_type(a.atttypid, a.atttypmod) as vector_type
                from pg_attribute a
                join pg_class c on c.oid = a.attrelid
                join pg_namespace n on n.oid = c.relnamespace
                where n.nspname = current_schema()
                  and c.relname = $1
                  and a.attname = 'embedding'
                  and not a.attisdropped
                """,
                table,
            )
            if row is None:
                continue
            if str(row["vector_type"]) != f"vector({self.embedding_dimensions})":
                await conn.execute(f"drop table if exists {table} cascade")

    async def upsert_document(self, document: IndexedDocument) -> bool:
        chunks = chunk_markdown(document.markdown)
        if await self._document_index_current(document, chunks):
            return False
        embeddings = await self.embedding_provider.embed_documents(
            [embedding_input(document.title, text, alias_text=document.alias_text) for text in chunks]
        )
        self._validate_embeddings(embeddings)
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    insert into kb_documents (
                        document_id, space_id, site_id, title, source_url, alias_text, published_at,
                        content_hash, markdown_path, raw_html_path, quality_json, status, updated_at
                    )
                    values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, 'active', now())
                    on conflict(document_id) do update set
                        space_id=excluded.space_id,
                        site_id=excluded.site_id,
                        title=excluded.title,
                        source_url=excluded.source_url,
                        alias_text=excluded.alias_text,
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
                    document.alias_text,
                    document.published_at,
                    document.content_hash,
                    document.markdown_path,
                    document.raw_html_path,
                    json.dumps(document.quality, ensure_ascii=False),
                )
                await conn.execute("delete from kb_chunks where document_id = $1", document.document_id)
                for index, text in enumerate(chunks):
                    embedding = embeddings[index]
                    chunk_id = f"{document.document_id}:{index}"
                    await conn.execute(
                        """
                        insert into kb_chunks (
                            chunk_id, document_id, space_id, chunk_index, title, source_url,
                            alias_text, published_at, text, search_text, embedding, embedding_provider,
                            embedding_model, embedding_dimensions
                        )
                        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::vector, $12, $13, $14)
                        """,
                        chunk_id,
                        document.document_id,
                        document.space_id,
                        index,
                        document.title,
                        document.source_url,
                        document.alias_text,
                        document.published_at,
                        text,
                        searchable_text(f"{document.title}\n{document.alias_text}\n{text}"),
                        vector_literal(embedding),
                        self.embedding_provider.provider_id,
                        self.embedding_provider.model,
                        len(embedding),
                    )
        return True

    async def _document_index_current(self, document: IndexedDocument, chunks: list[str]) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                select title, source_url, alias_text, published_at, content_hash,
                       markdown_path, raw_html_path, quality_json, status
                from kb_documents
                where document_id = $1
                """,
                document.document_id,
            )
            if row is None:
                return False
            stored_quality = row["quality_json"]
            if isinstance(stored_quality, str):
                stored_quality = json.loads(stored_quality)
            if dict(stored_quality or {}) != document.quality:
                return False
            if (
                str(row["title"]) != document.title
                or str(row["source_url"]) != document.source_url
                or str(row["alias_text"] or "") != document.alias_text
                or row["published_at"] != document.published_at
                or str(row["content_hash"]) != document.content_hash
                or str(row["markdown_path"]) != document.markdown_path
                or str(row["raw_html_path"]) != document.raw_html_path
                or str(row["status"]) != "active"
            ):
                return False
            chunk_rows = await conn.fetch(
                """
                select chunk_index, title, source_url, alias_text, published_at, text,
                       search_text, embedding_provider, embedding_model, embedding_dimensions
                from kb_chunks
                where document_id = $1
                order by chunk_index
                """,
                document.document_id,
            )
        if len(chunk_rows) != len(chunks):
            return False
        for index, text in enumerate(chunks):
            row = chunk_rows[index]
            if int(row["chunk_index"]) != index:
                return False
            if (
                str(row["title"]) != document.title
                or str(row["source_url"]) != document.source_url
                or str(row["alias_text"] or "") != document.alias_text
                or row["published_at"] != document.published_at
                or str(row["text"]) != text
                or str(row["search_text"]) != searchable_text(f"{document.title}\n{document.alias_text}\n{text}")
                or str(row["embedding_provider"]) != self.embedding_provider.provider_id
                or str(row["embedding_model"]) != self.embedding_provider.model
                or int(row["embedding_dimensions"]) != self.embedding_dimensions
            ):
                return False
        return True

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
            await conn.execute(
                """
                delete from kb_document_links
                where from_document_id = any($1::text[]) or to_document_id = any($1::text[])
                """,
                stale_ids,
            )

    async def replace_site_document_links(self, *, site_id: str, links: list[IndexedDocumentLink]) -> int:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("delete from kb_document_links where site_id = $1", site_id)
                count = 0
                for link in links:
                    if not link.from_document_id or not link.to_document_id:
                        continue
                    await conn.execute(
                        """
                        insert into kb_document_links (
                            site_id, from_document_id, to_document_id, from_url, to_url,
                            link_text, link_type, metadata_json, updated_at
                        )
                        values ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, now())
                        on conflict(site_id, from_document_id, to_document_id, link_text) do update set
                            from_url=excluded.from_url,
                            to_url=excluded.to_url,
                            link_type=excluded.link_type,
                            metadata_json=excluded.metadata_json,
                            updated_at=now()
                        """,
                        link.site_id,
                        link.from_document_id,
                        link.to_document_id,
                        link.from_url,
                        link.to_url,
                        link.link_text,
                        link.link_type,
                        json.dumps(link.metadata or {}, ensure_ascii=False),
                    )
                    count += 1
        return count

    async def search(
        self,
        *,
        queries: list[str],
        space_ids: list[str],
        entity_matches: tuple[EntityMatch, ...],
        top_k: int,
    ) -> list[RetrievedChunk]:
        route_queries = dedupe_queries(queries)
        search_space_ids = dedupe_space_ids(space_ids)
        if not route_queries:
            return []
        query_vectors = await self.embedding_provider.embed_queries(route_queries)
        self._validate_embeddings(query_vectors)
        candidate_limit = max(50, top_k * 12)
        ranked_lists: list[tuple[str, float, list[dict[str, Any]]]] = []
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            typed_conn = cast(asyncpg.Connection, conn)
            entity = await self._entity_candidates(
                typed_conn,
                entity_matches=entity_matches,
                space_ids=search_space_ids,
                limit=candidate_limit,
            )
            ranked_lists.append(("entity", ENTITY_RRF_WEIGHT, entity))
            for route_index, (route_query, query_vector) in enumerate(zip(route_queries, query_vectors, strict=True)):
                title = await self._title_candidates(
                    typed_conn,
                    query=route_query,
                    space_ids=search_space_ids,
                    limit=candidate_limit,
                )
                bm25 = await self._bm25_candidates(
                    typed_conn,
                    query=route_query,
                    space_ids=search_space_ids,
                    limit=candidate_limit,
                )
                vector = await self._vector_candidates(
                    typed_conn,
                    query_vector=query_vector,
                    space_ids=search_space_ids,
                    limit=candidate_limit,
                )
                route_name = f"route_{route_index + 1}"
                route_factor = retrieval_route_weight(route_index, route_count=len(route_queries))
                ranked_lists.extend(
                    [
                        (f"{route_name}:title", route_factor * TITLE_RRF_WEIGHT, title),
                        (f"{route_name}:vector", route_factor * VECTOR_RRF_WEIGHT, vector),
                        (f"{route_name}:bm25", route_factor * BM25_RRF_WEIGHT, bm25),
                    ]
                )

        scored = fuse_ranked_candidates(ranked_lists)
        scored.sort(
            key=lambda item: (
                float(item.get("score") or 0.0),
                float(item.get("best_raw_score") or 0.0),
            ),
            reverse=True,
        )
        scored_for_rerank = diversify_candidates_for_rerank(scored)
        route_metadata = [{"route": f"route_{index + 1}", "query": route_query} for index, route_query in enumerate(route_queries)]
        reranked = await self.reranker.rerank(
            question=route_queries[0],
            candidates=[
                RerankCandidate(
                    candidate_id=str(item["chunk_id"]),
                    title=rerank_title(str(item["title"]), str(item.get("alias_text") or "")),
                    text=str(item["text"]),
                    source=str(item["source_url"]),
                    initial_score=float(item.get("score") or 0.0),
                )
                for item in scored_for_rerank
            ],
            top_k=min(len(scored), max(top_k * DOCUMENT_DEDUP_RERANK_MULTIPLIER, top_k)),
        )
        reranked = [item for item in reranked if item.score >= self.min_rerank_score]
        by_chunk_id = {str(item["chunk_id"]): item for item in scored}
        reranked_pages = group_reranks_by_content(reranked, by_chunk_id, top_k=top_k)
        selected_reranked = [reranked_item for page in reranked_pages for reranked_item in page]
        context_by_chunk_id = await self._expanded_context_by_chunk(
            hits=[by_chunk_id[reranked_item.candidate.candidate_id] for reranked_item in selected_reranked],
            query=route_queries[0],
            space_ids=search_space_ids,
        )
        chunks: list[RetrievedChunk] = []
        for page_reranks in reranked_pages:
            reranked_item = page_reranks[0]
            item = by_chunk_id[reranked_item.candidate.candidate_id]
            page_items = [by_chunk_id[page_item.candidate.candidate_id] for page_item in page_reranks]
            expanded_text = combine_page_contexts(
                [
                    context_by_chunk_id.get(str(page_item["chunk_id"])) or str(page_item["text"])
                    for page_item in page_items
                ]
            )
            rrf_score = float(item.get("score") or 0.0)
            item["rrf_score"] = rrf_score
            item["rerank_score"] = reranked_item.score
            item["rerank_rationale"] = reranked_item.rationale
            item["score"] = reranked_item.score
            item["expanded_text"] = expanded_text
            item["page_chunk_matches"] = [
                {
                    "chunk_id": page_item.candidate.candidate_id,
                    "chunk_index": by_chunk_id[page_item.candidate.candidate_id].get("chunk_index"),
                    "rerank_score": page_item.score,
                    "rerank_rationale": page_item.rationale,
                }
                for page_item in page_reranks
            ]
            metadata = {
                "document_id": item["document_id"],
                "content_hash": item.get("content_hash"),
                "chunk_id": item["chunk_id"],
                "chunk_index": item.get("chunk_index"),
                "page_chunk_matches": item["page_chunk_matches"],
                "score": item["score"],
                "rrf_score": item["rrf_score"],
                "rerank_score": item["rerank_score"],
                "rerank_rationale": item["rerank_rationale"],
                "title_score": item.get("title_score", 0.0),
                "entity_score": item.get("entity_score", 0.0),
                "bm25_score": item.get("bm25_score", 0.0),
                "vector_score": item.get("vector_score", 0.0),
                "best_rank": item.get("best_rank"),
                "best_raw_score": item.get("best_raw_score", 0.0),
                "retrieval_space_ids": search_space_ids,
                "retrieval_routes": route_metadata,
                "matched_entities": item.get("matched_entities", []),
                "retrieval_matches": item.get("retrieval_matches", []),
                "embedding_model": item.get("embedding_model"),
            }
            citation = Citation(
                title=str(item["title"]),
                source=str(item["source_url"]),
                snippet=str(item["text"])[:500],
                published_at=item.get("published_at"),
                metadata=metadata,
            )
            chunks.append(
                RetrievedChunk(
                    text=expanded_text,
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
        elif collection in STRUCTURED_FILTER_FIELDS:
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
            data = json_object(row["payload_json"])
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

    async def search_kb_items(
        self,
        *,
        query: str,
        space_id: str,
        item_types: list[str] | None = None,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        query_vector = (await self.embedding_provider.embed_queries([query]))[0]
        self._validate_embeddings([query_vector])
        type_clause = "and (cardinality($2::text[]) = 0 or item_type = any($2::text[]))"
        searchable_space_ids = [space_id]
        if item_types == ["entity"] and space_id != GLOBAL_ENTITY_SPACE_ID:
            searchable_space_ids.append(GLOBAL_ENTITY_SPACE_ID)
        normalized_query = normalize_entity_text(query)
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                with exact_entity_candidates as (
                    select distinct on (i.item_id)
                           i.*,
                           (10000.0 + length(a.normalized_alias)::float + a.confidence) as score
                    from kb_entity_aliases a
                    join kb_search_items i on i.entity_id = a.entity_id and i.item_type = 'entity'
                    where a.review_status = 'approved'
                      and i.review_status = 'approved'
                      and ($1 = '' or i.space_id = any($6::text[]))
                      and ($7 <> '' and $7 like '%' || a.normalized_alias || '%')
                      {type_clause}
                    order by i.item_id, length(a.normalized_alias) desc, a.confidence desc
                    limit $3
                ),
                vector_candidates as (
                    select *, (1 - (embedding <=> $5::vector)) as score
                    from kb_search_items
                    where review_status = 'approved'
                      and ($1 = '' or space_id = any($6::text[]))
                      {type_clause}
                    order by embedding <=> $5::vector
                    limit $3
                ),
                bm25_candidates as (
                    select *, pdb.score(item_id) as score
                    from kb_search_items
                    where review_status = 'approved'
                      and ($1 = '' or space_id = any($6::text[]))
                      {type_clause}
                      and (title ||| $4 or content_text ||| $4)
                    order by pdb.score(item_id) desc
                    limit $3
                ),
                candidates as (
                    select * from exact_entity_candidates
                    union all
                    select * from vector_candidates
                    union all
                    select * from bm25_candidates
                ),
                ranked as (
                    select distinct on (item_id) *
                    from candidates
                    order by item_id, score desc
                )
                select *
                from ranked
                order by score desc
                limit $3
                """,
                space_id,
                item_types or [],
                limit,
                parade_query_text(query),
                vector_literal(query_vector),
                searchable_space_ids,
                normalized_query,
            )
        return [record_to_dict(row) for row in rows]

    async def fetch_entity_relations(self, *, space_id: str, entity_ids: list[str]) -> list[dict[str, Any]]:
        if not entity_ids:
            return []
        searchable_space_ids = [space_id]
        if space_id != GLOBAL_ENTITY_SPACE_ID:
            searchable_space_ids.append(GLOBAL_ENTITY_SPACE_ID)
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                select r.space_id, r.subject_entity_id, r.predicate, r.object_entity_id,
                       r.confidence, r.metadata_json,
                       s.entity_type as subject_type, s.canonical_name as subject_name, s.metadata_json as subject_metadata,
                       o.entity_type as object_type, o.canonical_name as object_name, o.metadata_json as object_metadata
                from kb_entity_relations r
                join kb_entities s on s.entity_id = r.subject_entity_id
                join kb_entities o on o.entity_id = r.object_entity_id
                where r.review_status = 'approved'
                  and s.review_status = 'approved'
                  and o.review_status = 'approved'
                  and ($1 = '' or r.space_id = any($3::text[]))
                  and (r.subject_entity_id = any($2::text[]) or r.object_entity_id = any($2::text[]))
                """,
                space_id,
                entity_ids,
                searchable_space_ids,
            )
        return [record_to_dict(row) for row in rows]

    async def clear_kb_search_items(self, space_id: str) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("delete from kb_search_items where space_id = $1", space_id)

    async def upsert_kb_search_items(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        embeddings = await self.embedding_provider.embed_documents([str(row["content_text"]) for row in rows])
        self._validate_embeddings(embeddings)
        pool = await self._get_pool()
        count = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                for item, embedding in zip(rows, embeddings, strict=True):
                    await conn.execute(
                        """
                        insert into kb_search_items (
                            item_id, space_id, item_type, entity_id, fact_table, fact_key,
                            document_id, chunk_id, title, content_text, search_text,
                            metadata_json, embedding, embedding_provider, embedding_model,
                            embedding_dimensions, review_status, updated_at
                        )
                        values (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                            $12::jsonb, $13::vector, $14, $15, $16, 'approved', now()
                        )
                        on conflict(item_id) do update set
                            space_id=excluded.space_id,
                            item_type=excluded.item_type,
                            entity_id=excluded.entity_id,
                            fact_table=excluded.fact_table,
                            fact_key=excluded.fact_key,
                            document_id=excluded.document_id,
                            chunk_id=excluded.chunk_id,
                            title=excluded.title,
                            content_text=excluded.content_text,
                            search_text=excluded.search_text,
                            metadata_json=excluded.metadata_json,
                            embedding=excluded.embedding,
                            embedding_provider=excluded.embedding_provider,
                            embedding_model=excluded.embedding_model,
                            embedding_dimensions=excluded.embedding_dimensions,
                            review_status='approved',
                            updated_at=now()
                        """,
                        item["item_id"],
                        item["space_id"],
                        item["item_type"],
                        item.get("entity_id"),
                        item.get("fact_table") or "",
                        item.get("fact_key") or "",
                        item.get("document_id"),
                        item.get("chunk_id"),
                        item["title"],
                        item["content_text"],
                        searchable_text(str(item["content_text"])),
                        json.dumps(item.get("metadata") or item.get("metadata_json") or {}, ensure_ascii=False),
                        vector_literal(embedding),
                        self.embedding_provider.provider_id,
                        self.embedding_provider.model,
                        len(embedding),
                    )
                    count += 1
        return count

    async def upsert_kb_entities(self, rows: list[dict[str, Any]]) -> int:
        pool = await self._get_pool()
        count = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                for item in rows:
                    await conn.execute(
                        """
                        insert into kb_entities (
                            entity_id, space_id, entity_type, canonical_name, description,
                            source_collection, source_key, metadata_json, review_status, updated_at
                        )
                        values ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, 'approved', now())
                        on conflict(entity_id) do update set
                            space_id=excluded.space_id,
                            entity_type=excluded.entity_type,
                            canonical_name=excluded.canonical_name,
                            description=excluded.description,
                            source_collection=excluded.source_collection,
                            source_key=excluded.source_key,
                            metadata_json=excluded.metadata_json,
                            review_status='approved',
                            updated_at=now()
                        """,
                        item["entity_id"],
                        item["space_id"],
                        item["entity_type"],
                        item["canonical_name"],
                        item.get("description") or "",
                        item.get("source_collection") or "",
                        item.get("source_key") or "",
                        json.dumps(item.get("metadata") or item.get("metadata_json") or {}, ensure_ascii=False),
                    )
                    count += 1
        return count

    async def clear_kb_entities(self, space_id: str) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("delete from kb_entities where space_id = $1", space_id)

    async def upsert_kb_entity_aliases(self, rows: list[dict[str, Any]]) -> int:
        pool = await self._get_pool()
        count = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                for item in rows:
                    normalized_alias = item.get("normalized_alias") or normalize_entity_text(str(item["alias"]))
                    if not normalized_alias:
                        continue
                    await conn.execute(
                        """
                        insert into kb_entity_aliases (
                            entity_id, space_id, alias, normalized_alias, alias_type,
                            confidence, review_status, updated_at
                        )
                        values ($1, $2, $3, $4, $5, $6, 'approved', now())
                        on conflict(space_id, entity_id, normalized_alias) do update set
                            alias=excluded.alias,
                            alias_type=excluded.alias_type,
                            confidence=excluded.confidence,
                            review_status='approved',
                            updated_at=now()
                        """,
                        item["entity_id"],
                        item["space_id"],
                        item["alias"],
                        normalized_alias,
                        item.get("alias_type") or "alias",
                        float(item.get("confidence") or 1.0),
                    )
                    count += 1
        return count

    async def upsert_kb_entity_relations(self, rows: list[dict[str, Any]]) -> int:
        pool = await self._get_pool()
        count = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                for item in rows:
                    await conn.execute(
                        """
                        insert into kb_entity_relations (
                            space_id, subject_entity_id, predicate, object_entity_id,
                            confidence, metadata_json, review_status, updated_at
                        )
                        values ($1, $2, $3, $4, $5, $6::jsonb, 'approved', now())
                        on conflict(space_id, subject_entity_id, predicate, object_entity_id)
                        do update set
                            confidence=excluded.confidence,
                            metadata_json=excluded.metadata_json,
                            review_status='approved',
                            updated_at=now()
                        """,
                        item["space_id"],
                        item["subject_entity_id"],
                        item["predicate"],
                        item["object_entity_id"],
                        float(item.get("confidence") or 1.0),
                        json.dumps(item.get("metadata") or item.get("metadata_json") or {}, ensure_ascii=False),
                    )
                    count += 1
        return count

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

    async def upsert_admission_content_categories(self, rows: list[dict[str, Any]]) -> int:
        pool = await self._get_pool()
        count = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                for item in rows:
                    await conn.execute(
                        """
                        insert into admission_content_categories (
                            category_id, space_id, name, sort_order, source_url, source_document,
                            source_department, published_at, review_status, raw_json, updated_at
                        )
                        values ($1, $2, $3, $4, $5, $6, $7, $8, 'approved', $9::jsonb, now())
                        on conflict(category_id) do update set
                            space_id=excluded.space_id,
                            name=excluded.name,
                            sort_order=excluded.sort_order,
                            source_url=excluded.source_url,
                            source_document=excluded.source_document,
                            source_department=excluded.source_department,
                            published_at=excluded.published_at,
                            review_status='approved',
                            raw_json=excluded.raw_json,
                            updated_at=now()
                        """,
                        item["category_id"],
                        item["space_id"],
                        item["name"],
                        item.get("sort_order"),
                        item.get("source_url"),
                        item.get("source_document"),
                        item.get("source_department"),
                        item.get("published_at"),
                        json.dumps(item.get("raw_json") or {}, ensure_ascii=False),
                    )
                    count += 1
        return count

    async def upsert_admission_articles(self, rows: list[dict[str, Any]]) -> int:
        pool = await self._get_pool()
        count = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                for item in rows:
                    await conn.execute(
                        """
                        insert into admission_articles (
                            article_id, space_id, category_id, category_name, title, description,
                            source_url, logo_url, content_type, published_at, view_count,
                            source_document, source_department, source_text,
                            review_status, raw_json, updated_at
                        )
                        values (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                            $12, $13, $14, 'approved', $15::jsonb, now()
                        )
                        on conflict(article_id) do update set
                            space_id=excluded.space_id,
                            category_id=excluded.category_id,
                            category_name=excluded.category_name,
                            title=excluded.title,
                            description=excluded.description,
                            source_url=excluded.source_url,
                            logo_url=excluded.logo_url,
                            content_type=excluded.content_type,
                            published_at=excluded.published_at,
                            view_count=excluded.view_count,
                            source_document=excluded.source_document,
                            source_department=excluded.source_department,
                            source_text=excluded.source_text,
                            review_status='approved',
                            raw_json=excluded.raw_json,
                            updated_at=now()
                        """,
                        item["article_id"],
                        item["space_id"],
                        item.get("category_id"),
                        item.get("category_name") or "",
                        item["title"],
                        item.get("description") or "",
                        item.get("source_url"),
                        item.get("logo_url"),
                        item.get("content_type") or "",
                        item.get("published_at"),
                        item.get("view_count"),
                        item.get("source_document"),
                        item.get("source_department"),
                        item.get("source_text"),
                        json.dumps(item.get("raw_json") or {}, ensure_ascii=False),
                    )
                    count += 1
        return count

    async def upsert_academic_units(self, rows: list[dict[str, Any]]) -> int:
        pool = await self._get_pool()
        count = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                for item in rows:
                    await conn.execute(
                        """
                        insert into academic_units (
                            unit_id, space_id, name, sort_order, source_url, source_document,
                            source_department, published_at, review_status, raw_json, updated_at
                        )
                        values ($1, $2, $3, $4, $5, $6, $7, $8, 'approved', $9::jsonb, now())
                        on conflict(unit_id) do update set
                            space_id=excluded.space_id,
                            name=excluded.name,
                            sort_order=excluded.sort_order,
                            source_url=excluded.source_url,
                            source_document=excluded.source_document,
                            source_department=excluded.source_department,
                            published_at=excluded.published_at,
                            review_status='approved',
                            raw_json=excluded.raw_json,
                            updated_at=now()
                        """,
                        item["unit_id"],
                        item["space_id"],
                        item["name"],
                        item.get("sort_order"),
                        item.get("source_url"),
                        item.get("source_document"),
                        item.get("source_department"),
                        item.get("published_at"),
                        json.dumps(item.get("raw_json") or {}, ensure_ascii=False),
                    )
                    count += 1
        return count

    async def upsert_admission_schools(self, rows: list[dict[str, Any]]) -> int:
        pool = await self._get_pool()
        count = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                for item in rows:
                    await conn.execute(
                        """
                        insert into admission_schools (
                            school_id, space_id, unit_id, unit_name, name, official_url, logo_url,
                            sort_order, source_url, source_document, source_department,
                            published_at, review_status, raw_json, updated_at
                        )
                        values (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                            $11, $12, 'approved', $13::jsonb, now()
                        )
                        on conflict(school_id) do update set
                            space_id=excluded.space_id,
                            unit_id=excluded.unit_id,
                            unit_name=excluded.unit_name,
                            name=excluded.name,
                            official_url=excluded.official_url,
                            logo_url=excluded.logo_url,
                            sort_order=excluded.sort_order,
                            source_url=excluded.source_url,
                            source_document=excluded.source_document,
                            source_department=excluded.source_department,
                            published_at=excluded.published_at,
                            review_status='approved',
                            raw_json=excluded.raw_json,
                            updated_at=now()
                        """,
                        item["school_id"],
                        item["space_id"],
                        item.get("unit_id"),
                        item.get("unit_name") or "",
                        item["name"],
                        item.get("official_url") or "",
                        item.get("logo_url") or "",
                        item.get("sort_order"),
                        item.get("source_url"),
                        item.get("source_document"),
                        item.get("source_department"),
                        item.get("published_at"),
                        json.dumps(item.get("raw_json") or {}, ensure_ascii=False),
                    )
                    count += 1
        return count

    async def upsert_admission_media_items(self, rows: list[dict[str, Any]]) -> int:
        pool = await self._get_pool()
        count = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                for item in rows:
                    await conn.execute(
                        """
                        insert into admission_media_items (
                            item_id, space_id, category_id, category_name, title, item_type,
                            source_url, media_url, logo_url, description, published_at,
                            source_document, source_department, source_text,
                            review_status, raw_json, updated_at
                        )
                        values (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                            $11, $12, $13, $14, 'approved', $15::jsonb, now()
                        )
                        on conflict(item_id) do update set
                            space_id=excluded.space_id,
                            category_id=excluded.category_id,
                            category_name=excluded.category_name,
                            title=excluded.title,
                            item_type=excluded.item_type,
                            source_url=excluded.source_url,
                            media_url=excluded.media_url,
                            logo_url=excluded.logo_url,
                            description=excluded.description,
                            published_at=excluded.published_at,
                            source_document=excluded.source_document,
                            source_department=excluded.source_department,
                            source_text=excluded.source_text,
                            review_status='approved',
                            raw_json=excluded.raw_json,
                            updated_at=now()
                        """,
                        item["item_id"],
                        item["space_id"],
                        item.get("category_id") or "",
                        item.get("category_name") or "",
                        item["title"],
                        item.get("item_type") or "",
                        item.get("source_url"),
                        item.get("media_url") or "",
                        item.get("logo_url") or "",
                        item.get("description") or "",
                        item.get("published_at"),
                        item.get("source_document"),
                        item.get("source_department"),
                        item.get("source_text"),
                        json.dumps(item.get("raw_json") or {}, ensure_ascii=False),
                    )
                    count += 1
        return count

    async def upsert_majors(self, rows: list[dict[str, Any]]) -> int:
        pool = await self._get_pool()
        count = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                for item in rows:
                    await conn.execute(
                        """
                        insert into majors (
                            space_id, name, school_name, degree, category, source_url,
                            source_document, source_text, source_department, published_at,
                            review_status, raw_json, updated_at
                        )
                        values (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                            'approved', $11::jsonb, now()
                        )
                        on conflict(space_id, name) do update set
                            school_name=excluded.school_name,
                            degree=excluded.degree,
                            category=excluded.category,
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
                        item["name"],
                        item.get("school_name"),
                        item.get("degree"),
                        item.get("category"),
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
        space_ids: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        query_compact = compact_text(query)
        if not query_compact:
            return []
        rows = await conn.fetch(
            """
            select c.chunk_id, c.document_id, d.content_hash, c.chunk_index, d.space_id, c.title, c.source_url, c.published_at, c.text,
                   c.alias_text, c.embedding_model
            from kb_chunks c
            join kb_documents d on d.document_id = c.document_id
            where c.chunk_index = 0 and d.status = 'active'
              and (cardinality($1::text[]) = 0 or d.space_id = any($1::text[]))
            """,
            space_ids,
        )
        items = [record_to_dict(row) for row in rows]
        candidates: list[dict[str, Any]] = []
        for item in items:
            title_text = title_candidate_text(str(item["title"]), str(item.get("alias_text") or ""))
            title = compact_text(title_text)
            if not title:
                continue
            overlap = title_overlap_score(
                query_compact=query_compact,
                title=title,
            )
            if is_site_entry_url(str(item.get("source_url") or "")) and title != query_compact:
                overlap = min(overlap, 0.8)
            if title in query_compact:
                item["title_score"] = overlap
                candidates.append(item)
            elif overlap > 0:
                item["title_score"] = overlap
                candidates.append(item)
        candidates.sort(key=lambda item: item["title_score"], reverse=True)
        return await self._expand_strong_title_documents(conn, candidates[:limit], limit=limit)

    async def _expand_strong_title_documents(
        self,
        conn: asyncpg.Connection,
        candidates: list[dict[str, Any]],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        strong_by_document = {
            str(item["document_id"]): float(item.get("title_score") or 0.0)
            for item in candidates
            if float(item.get("title_score") or 0.0) >= 3.0
        }
        if not strong_by_document:
            return candidates
        rows = await conn.fetch(
            """
            select c.chunk_id, c.document_id, d.content_hash, c.chunk_index, d.space_id, c.title, c.source_url, c.published_at, c.text,
                   c.alias_text, c.embedding_model
            from kb_chunks c
            join kb_documents d on d.document_id = c.document_id
            where c.document_id = any($1::text[]) and c.chunk_index > 0
            order by c.document_id, c.chunk_index
            """,
            list(strong_by_document),
        )
        seen = {str(item["chunk_id"]) for item in candidates}
        expanded = list(candidates)
        for row in rows:
            item = record_to_dict(row)
            if str(item["chunk_id"]) in seen:
                continue
            item["title_score"] = strong_by_document[str(item["document_id"])] * 0.96
            expanded.append(item)
            seen.add(str(item["chunk_id"]))
        expanded.sort(key=lambda item: float(item.get("title_score") or 0.0), reverse=True)
        return expanded[:limit]

    async def _entity_candidates(
        self,
        conn: asyncpg.Connection,
        *,
        entity_matches: tuple[EntityMatch, ...],
        space_ids: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        strong_matches = [match for match in entity_matches if is_high_confidence_entity_match(match)]
        if not strong_matches:
            return []
        score_by_entity_id: dict[str, float] = {}
        matched_entity_by_id: dict[str, dict[str, Any]] = {}
        for match in strong_matches:
            score = entity_match_retrieval_score(match)
            if score <= score_by_entity_id.get(match.entity_id, 0.0):
                continue
            score_by_entity_id[match.entity_id] = score
            matched_entity_by_id[match.entity_id] = {
                "entity_id": match.entity_id,
                "entity_type": match.entity_type,
                "canonical_name": match.canonical_name,
                "matched_alias": match.matched_alias or match.canonical_name,
                "alias_type": match.alias_type,
                "score": match.score,
            }
        rows = await conn.fetch(
            """
            select distinct on (c.chunk_id)
                   c.chunk_id, c.document_id, d.content_hash, c.chunk_index, d.space_id, c.title, c.source_url, c.published_at,
                   c.text, c.alias_text, c.embedding_model, i.entity_id
            from kb_search_items i
            join kb_chunks c on (
                (i.chunk_id is not null and i.chunk_id <> '' and c.chunk_id = i.chunk_id)
                or
                ((i.chunk_id is null or i.chunk_id = '') and i.document_id is not null and i.document_id <> '' and c.document_id = i.document_id)
            )
            join kb_documents d on d.document_id = c.document_id
            where i.review_status = 'approved'
              and i.entity_id = any($1::text[])
              and d.status = 'active'
              and (cardinality($2::text[]) = 0 or d.space_id = any($2::text[]))
            order by c.chunk_id,
                     case when i.chunk_id = c.chunk_id then 0 else 1 end,
                     c.chunk_index
            limit $3
            """,
            list(score_by_entity_id),
            space_ids,
            limit,
        )
        items = [record_to_dict(row) for row in rows]
        for item in items:
            entity_id = str(item.get("entity_id") or "")
            item["entity_score"] = score_by_entity_id.get(entity_id, 0.0)
            item["matched_entities"] = [matched_entity_by_id[entity_id]] if entity_id in matched_entity_by_id else []
        items.sort(key=lambda item: float(item.get("entity_score") or 0.0), reverse=True)
        return items[:limit]

    async def _bm25_candidates(
        self,
        conn: asyncpg.Connection,
        *,
        query: str,
        space_ids: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        search_query = parade_query_text(query)
        if not search_query:
            return []
        rows = await conn.fetch(
            """
            select c.chunk_id, c.document_id, d.content_hash, c.chunk_index, d.space_id, c.title, c.source_url, c.published_at, c.text,
                   c.alias_text, c.embedding_model,
                   pdb.score(c.chunk_id) as bm25_score
            from kb_chunks c
            join kb_documents d on d.document_id = c.document_id
            where d.status = 'active'
              and (cardinality($2::text[]) = 0 or c.space_id = any($2::text[]))
              and (c.title ||| $1 or c.alias_text ||| $1 or c.search_text ||| $1)
            order by pdb.score(c.chunk_id) desc
            limit $3
            """,
            search_query,
            space_ids,
            limit,
        )
        items = [record_to_dict(row) for row in rows]
        for item in items:
            item["bm25_score"] = float(item.get("bm25_score") or 0.0)
        return items

    async def _vector_candidates(
        self,
        conn: asyncpg.Connection,
        *,
        query_vector: list[float],
        space_ids: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = await conn.fetch(
            """
            select c.chunk_id, c.document_id, d.content_hash, c.chunk_index, d.space_id, c.title, c.source_url, c.published_at, c.text,
                   c.alias_text, c.embedding_model,
                   1 - (c.embedding <=> $1::vector) as vector_score
            from kb_chunks c
            join kb_documents d on d.document_id = c.document_id
            where d.status = 'active'
              and (cardinality($2::text[]) = 0 or d.space_id = any($2::text[]))
            order by c.embedding <=> $1::vector
            limit $3
            """,
            vector_literal(query_vector),
            space_ids,
            limit,
        )
        return [record_to_dict(row) for row in rows]

    async def _expanded_context_by_chunk(
        self,
        *,
        hits: list[dict[str, Any]],
        query: str,
        space_ids: list[str],
    ) -> dict[str, str]:
        if not hits:
            return {}
        neighbor_rows = await self._neighbor_context_rows(hits=hits, space_ids=space_ids)
        linked_rows = await self._linked_context_rows(hits=hits, query=query, space_ids=space_ids)
        neighbor_by_chunk = group_neighbor_context(hits=hits, rows=neighbor_rows)
        linked_by_chunk = group_linked_context(hits=hits, rows=linked_rows, query=query)
        expanded: dict[str, str] = {}
        for hit in hits:
            chunk_id = str(hit["chunk_id"])
            expanded[chunk_id] = build_expanded_chunk_text(
                hit=hit,
                neighbors=neighbor_by_chunk.get(chunk_id, []),
                linked=linked_by_chunk.get(chunk_id, []),
            )
        return expanded

    async def _neighbor_context_rows(
        self,
        *,
        hits: list[dict[str, Any]],
        space_ids: list[str],
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        for hit in hits:
            document_id = str(hit.get("document_id") or "")
            chunk_index = int(hit.get("chunk_index") or 0)
            if not document_id:
                continue
            start_index = len(values) + 1
            values.extend(
                [
                    document_id,
                    max(0, chunk_index - CONTEXT_NEIGHBOR_RADIUS),
                    chunk_index + CONTEXT_NEIGHBOR_RADIUS,
                ]
            )
            clauses.append(
                f"(c.document_id = ${start_index} and c.chunk_index between ${start_index + 1} and ${start_index + 2})"
            )
        if not clauses:
            return []
        values.append(space_ids)
        space_index = len(values)
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                select c.chunk_id, c.document_id, c.chunk_index, d.space_id, c.title,
                       c.source_url, c.published_at, c.text
                from kb_chunks c
                join kb_documents d on d.document_id = c.document_id
                where ({' or '.join(clauses)})
                  and d.status = 'active'
                  and (cardinality(${space_index}::text[]) = 0 or d.space_id = any(${space_index}::text[]))
                order by c.document_id, c.chunk_index
                """,
                *values,
            )
        return [record_to_dict(row) for row in rows]

    async def _linked_context_rows(
        self,
        *,
        hits: list[dict[str, Any]],
        query: str,
        space_ids: list[str],
    ) -> list[dict[str, Any]]:
        del query
        document_ids = dedupe_space_ids([str(hit.get("document_id") or "") for hit in hits])
        if not document_ids:
            return []
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                select l.site_id, l.from_document_id, l.to_document_id, l.from_url, l.to_url,
                       l.link_text, l.link_type,
                       c.chunk_id, c.document_id, c.chunk_index, d.space_id, c.title,
                       c.source_url, c.published_at, c.text
                from kb_document_links l
                join kb_chunks c on (
                    (l.from_document_id = any($1::text[]) and c.document_id = l.to_document_id and c.chunk_index = 0)
                    or
                    (l.to_document_id = any($1::text[]) and c.document_id = l.from_document_id and c.chunk_index = 0)
                )
                join kb_documents d on d.document_id = c.document_id
                where (l.from_document_id = any($1::text[]) or l.to_document_id = any($1::text[]))
                  and l.link_type = 'content_link'
                  and d.status = 'active'
                  and (cardinality($2::text[]) = 0 or d.space_id = any($2::text[]))
                """,
                document_ids,
                space_ids,
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


EXTRA_STRUCTURED_FILTER_FIELDS: dict[str, set[str]] = {
    "kb_entities": {
        "entity_id",
        "space_id",
        "entity_type",
        "canonical_name",
        "source_collection",
        "source_key",
        "review_status",
    },
    "kb_entity_aliases": {
        "entity_id",
        "space_id",
        "alias",
        "normalized_alias",
        "alias_type",
        "review_status",
    },
    "kb_entity_relations": {
        "space_id",
        "subject_entity_id",
        "predicate",
        "object_entity_id",
        "review_status",
    },
    "admission_content_categories": {"space_id", "category_id", "name", "review_status"},
}

STRUCTURED_FILTER_FIELDS: dict[str, set[str]] = {
    **KnowledgeSemanticLayer().filter_fields_by_table(),
    **EXTRA_STRUCTURED_FILTER_FIELDS,
}


def chunk_markdown(markdown: str, *, target_chars: int = 800, overlap_chars: int = 120) -> list[str]:
    sections = split_markdown_sections(markdown)
    chunks: list[str] = []
    current = ""
    for section in sections:
        if len(current) + len(section) + 2 <= target_chars:
            current = f"{current}\n\n{section}".strip()
            continue
        if current:
            chunks.append(current)
        split_chunks = split_long_section(section, target_chars=target_chars, overlap_chars=overlap_chars)
        if len(split_chunks) > 1:
            chunks.extend(split_chunks)
            current = ""
        else:
            current = split_chunks[0] if split_chunks else ""
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


def split_long_section(section: str, *, target_chars: int, overlap_chars: int) -> list[str]:
    if len(section) <= target_chars:
        return [section.strip()]
    heading = first_markdown_heading(section)
    body = section.strip()
    chunks: list[str] = []
    while len(body) > target_chars:
        segment = body[:target_chars].strip()
        chunks.append(with_section_heading(segment, heading))
        body = body[target_chars - overlap_chars :].strip()
    if body:
        chunks.append(with_section_heading(body, heading))
    return chunks


def first_markdown_heading(text: str) -> str:
    for line in text.splitlines():
        clean = line.strip()
        if clean.startswith("#"):
            return clean
    return ""


def with_section_heading(text: str, heading: str) -> str:
    clean = text.strip()
    if not heading or clean.startswith(heading):
        return clean
    return f"{heading}\n\n{clean}".strip()


def embedding_input(title: str, text: str, *, alias_text: str = "") -> str:
    return "\n\n".join(
        part.strip()
        for part in (title, alias_text, text)
        if part and part.strip()
    ).strip()


def title_candidate_text(title: str, alias_text: str) -> str:
    return "\n".join(
        part.strip()
        for part in (title, alias_text)
        if part and part.strip()
    )


def rerank_title(title: str, alias_text: str) -> str:
    clean_heading = alias_text.strip()
    if not clean_heading:
        return title
    return f"{title}\n结构入口：{clean_heading[:300]}"


def parade_query_text(query: str) -> str:
    return re.sub(r"\s+", " ", query).strip()[:240]


def is_high_confidence_entity_match(match: EntityMatch) -> bool:
    return match.score >= 100.0 or match.alias_type == "relation_resolution"


def entity_match_retrieval_score(match: EntityMatch) -> float:
    if match.alias_type == "relation_resolution":
        return 12.0
    return min(12.0, 8.0 + max(0.0, match.score - 100.0) / 8.0)


def dedupe_queries(queries: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for query in queries:
        clean_query = query.strip()
        normalized = compact_text(clean_query)
        if not clean_query or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(clean_query)
    return result


def dedupe_space_ids(space_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for space_id in space_ids:
        clean_space_id = str(space_id or "").strip()
        if not clean_space_id or clean_space_id in seen:
            continue
        seen.add(clean_space_id)
        result.append(clean_space_id)
    return result


def fuse_ranked_candidates(
    ranked_lists: list[tuple[str, float, list[dict[str, Any]]]],
    *,
    rrf_k: int = 60,
) -> list[dict[str, Any]]:
    combined: dict[str, dict[str, Any]] = {}
    for source, weight, rows in ranked_lists:
        for rank, row in enumerate(rows, start=1):
            chunk_id = str(row.get("chunk_id") or "")
            if not chunk_id:
                continue
            item = combined.setdefault(chunk_id, dict(row))
            merge_candidate_fields(item, row)
            raw_score = candidate_raw_score(row)
            item["score"] = float(item.get("score") or 0.0) + weight / (rrf_k + rank)
            item["best_rank"] = min(int(item.get("best_rank") or rank), rank)
            item["best_raw_score"] = max(float(item.get("best_raw_score") or 0.0), raw_score)
            item.setdefault("retrieval_matches", []).append(
                {
                    "source": source,
                    "rank": rank,
                    "weight": weight,
                    "raw_score": raw_score,
                }
            )
    return list(combined.values())


def diversify_candidates_for_rerank(
    candidates: list[dict[str, Any]],
    *,
    per_content_limit: int = 2,
) -> list[dict[str, Any]]:
    primary: list[dict[str, Any]] = []
    overflow: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for candidate in candidates:
        content_hash = str(candidate.get("content_hash") or "").strip()
        if not content_hash:
            raise BackendUnavailable("retrieval candidate missing content_hash")
        count = counts.get(content_hash, 0)
        counts[content_hash] = count + 1
        if count < per_content_limit:
            primary.append(candidate)
        else:
            overflow.append(candidate)
    return [*primary, *overflow]


def retrieval_route_weight(route_index: int, *, route_count: int) -> float:
    if route_count <= 1:
        return 1.0
    return 0.5 if route_index == 0 else 1.5


def merge_candidate_fields(item: dict[str, Any], row: dict[str, Any]) -> None:
    for key, value in row.items():
        if key in {"title_score", "entity_score", "bm25_score", "vector_score"}:
            item[key] = max(float(item.get(key) or 0.0), float(value or 0.0))
        elif key == "matched_entities":
            existing = list(item.get("matched_entities") or [])
            seen = {str(entity.get("entity_id") or "") for entity in existing if isinstance(entity, dict)}
            for entity in value or []:
                if not isinstance(entity, dict):
                    continue
                entity_id = str(entity.get("entity_id") or "")
                if entity_id and entity_id not in seen:
                    existing.append(entity)
                    seen.add(entity_id)
            item[key] = existing
        elif key not in item or item[key] in (None, ""):
            item[key] = value


def group_reranks_by_content(
    reranked: list[RerankedCandidate],
    by_chunk_id: dict[str, dict[str, Any]],
    *,
    top_k: int,
) -> list[list[RerankedCandidate]]:
    groups: list[list[RerankedCandidate]] = []
    by_content: dict[str, list[RerankedCandidate]] = {}
    seen_content: set[str] = set()
    for item in reranked:
        chunk_id = item.candidate.candidate_id
        candidate = by_chunk_id.get(chunk_id)
        if candidate is None:
            continue
        content_key = content_dedup_key(candidate)
        if content_key not in seen_content:
            if len(groups) >= top_k:
                continue
            seen_content.add(content_key)
            by_content[content_key] = []
            groups.append(by_content[content_key])
        by_content[content_key].append(item)
    return groups


def content_dedup_key(candidate: dict[str, Any]) -> str:
    value = str(candidate["content_hash"]).strip()
    if not value:
        raise BackendUnavailable("retrieval candidate is missing content_hash")
    return value


def combine_page_contexts(contexts: list[str]) -> str:
    unique_contexts: list[str] = []
    seen: set[str] = set()
    for context in contexts:
        clean = context.strip()
        key = compact_text(clean)
        if not clean or not key or key in seen:
            continue
        seen.add(key)
        unique_contexts.append(clean)
    if len(unique_contexts) == 1:
        return truncate_context_parts(unique_contexts, max_chars=PAGE_CONTEXT_MAX_CHARS)
    return truncate_context_parts(
        [f"【同页命中 {index}】\n{context}" for index, context in enumerate(unique_contexts, start=1)],
        max_chars=PAGE_CONTEXT_MAX_CHARS,
    )


def candidate_raw_score(row: dict[str, Any]) -> float:
    return max(
        float(row.get("title_score") or 0.0),
        float(row.get("entity_score") or 0.0),
        float(row.get("bm25_score") or 0.0),
        float(row.get("vector_score") or 0.0),
    )


def is_site_entry_url(url: str) -> bool:
    path = urlparse(url).path.rstrip("/")
    return path in {"", "/index.htm", "/index.html"}


def searchable_text(text: str) -> str:
    return text.strip()


def title_overlap_score(
    *,
    query_compact: str,
    title: str,
) -> float:
    if title == query_compact:
        return 10.0
    if title in query_compact:
        query_coverage = len(title) / max(len(query_compact), 1)
        return min(8.0, max(6.0, 5.0 + 3.0 * query_coverage))
    if query_compact in title:
        query_coverage = len(query_compact) / max(len(title), 1)
        return min(7.0, max(5.5, 4.2 + 2.0 * query_coverage))
    return 0.0


def group_neighbor_context(
    *,
    hits: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for hit in hits:
        chunk_id = str(hit["chunk_id"])
        document_id = str(hit["document_id"])
        hit_index = int(hit.get("chunk_index") or 0)
        candidates = [
            row
            for row in rows
            if str(row.get("document_id") or "") == document_id and str(row.get("chunk_id") or "") != chunk_id
        ]
        candidates.sort(key=lambda row: (abs(int(row.get("chunk_index") or 0) - hit_index), int(row.get("chunk_index") or 0)))
        grouped[chunk_id] = candidates
    return grouped


def group_linked_context(
    *,
    hits: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    query: str,
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for hit in hits:
        chunk_id = str(hit["chunk_id"])
        document_id = str(hit["document_id"])
        candidates = [
            row
            for row in rows
            if row.get("from_document_id") == document_id or row.get("to_document_id") == document_id
        ]
        candidates.sort(key=lambda row: link_context_score(query=query, row=row, hit_document_id=document_id), reverse=True)
        seen_docs: set[str] = set()
        selected: list[dict[str, Any]] = []
        for row in candidates:
            linked_document_id = str(row.get("document_id") or "")
            if not linked_document_id or linked_document_id in seen_docs:
                continue
            seen_docs.add(linked_document_id)
            selected.append(row)
            if len(selected) >= CONTEXT_LINK_LIMIT:
                break
        grouped[chunk_id] = selected
    return grouped


def link_context_score(*, query: str, row: dict[str, Any], hit_document_id: str) -> float:
    text = compact_text(
        " ".join(
            [
                str(row.get("link_text") or ""),
                str(row.get("title") or ""),
                str(row.get("text") or "")[:240],
            ]
        )
    )
    query_compact = compact_text(query)
    score = 1.0 if row.get("from_document_id") == hit_document_id else 0.8
    if query_compact and query_compact in text:
        score += 6.0
    for term in exact_query_terms(query):
        compact_term = compact_text(term)
        if len(compact_term) >= 2 and compact_term in text:
            score += min(3.0, len(compact_term) / 2.0)
    return score


def exact_query_terms(query: str) -> list[str]:
    terms = [query]
    terms.extend(re.findall(r"[A-Za-z0-9]{2,}|[\u4e00-\u9fff]{2,}", query))
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        compact = compact_text(term)
        if not compact or compact in seen:
            continue
        seen.add(compact)
        result.append(term)
    return result


def build_expanded_chunk_text(
    *,
    hit: dict[str, Any],
    neighbors: list[dict[str, Any]],
    linked: list[dict[str, Any]],
) -> str:
    parts = [f"【命中片段｜{hit.get('title')}】\n{str(hit.get('text') or '').strip()}"]
    if neighbors:
        parts.append(
            "【同页前后文】\n"
            + "\n\n".join(
                f"- chunk {row.get('chunk_index')}：{str(row.get('text') or '').strip()}"
                for row in sorted(neighbors, key=lambda item: int(item.get("chunk_index") or 0))
                if str(row.get("text") or "").strip()
            )
        )
    if linked:
        parts.append(
            "【链接相关页面】\n"
            + "\n\n".join(
                (
                    f"- {row.get('title')}（{row.get('source_url')}；链接文字：{row.get('link_text') or '无'}）\n"
                    f"{str(row.get('text') or '').strip()}"
                )
                for row in linked
                if str(row.get("text") or "").strip()
            )
        )
    return truncate_context_parts(parts, max_chars=CONTEXT_MAX_CHARS)


def truncate_context_parts(parts: list[str], *, max_chars: int) -> str:
    text = "\n\n".join(part.strip() for part in parts if part.strip())
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}\n\n【上下文已截断】"


def normalize_filter(filters: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    raw_clauses = filters.get("_and")
    clauses: list[Any] = raw_clauses if isinstance(raw_clauses, list) else []
    for clause in clauses:
        if not isinstance(clause, dict):
            continue
        for key, value in clause.items():
            if isinstance(value, dict) and "_eq" in value:
                normalized[key] = value["_eq"]
            elif isinstance(value, dict) and "_in" in value and isinstance(value["_in"], list):
                normalized[f"{key}_in"] = [str(item) for item in value["_in"]]
    for key, value in filters.items():
        if isinstance(value, dict):
            if "_eq" in value:
                normalized[key] = value["_eq"]
            elif "_in" in value and isinstance(value["_in"], list):
                normalized[f"{key}_in"] = [str(item) for item in value["_in"]]
        elif key != "_and":
            normalized[key] = value
    if (
        "id_in" not in normalized
        and "id" in filters
        and isinstance(filters["id"], dict)
        and "_in" in filters["id"]
        and isinstance(filters["id"]["_in"], list)
    ):
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
        if isinstance(value, uuid.UUID):
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


def json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}
