from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from luoying_bot.capabilities.knowledge_base.errors import BackendUnavailable
from luoying_bot.capabilities.knowledge_base.models import Citation, RetrievedChunk
from luoying_bot.capabilities.knowledge_base.ports import RagBackend, StructuredBackend


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


class LocalKnowledgeStore(RagBackend, StructuredBackend):
    def __init__(self, db_path: Path, *, vector_dimensions: int = 384):
        self.db_path = db_path
        self.vector_dimensions = vector_dimensions
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    async def upsert_document(self, document: IndexedDocument) -> None:
        chunks = chunk_markdown(document.markdown)
        with self._connect() as conn:
            conn.execute(
                """
                insert into kb_documents (
                    document_id, space_id, site_id, title, source_url, published_at,
                    content_hash, markdown_path, raw_html_path, quality_json, status, updated_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', datetime('now'))
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
                    updated_at=datetime('now')
                """,
                (
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
                ),
            )
            conn.execute("delete from kb_chunks where document_id = ?", (document.document_id,))
            conn.execute("delete from kb_chunks_fts where document_id = ?", (document.document_id,))
            for index, text in enumerate(chunks):
                chunk_id = f"{document.document_id}:{index}"
                embedding = json.dumps(hash_embedding(text, self.vector_dimensions))
                conn.execute(
                    """
                    insert into kb_chunks (
                        chunk_id, document_id, chunk_index, title, source_url,
                        published_at, text, embedding_json
                    )
                    values (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        document.document_id,
                        index,
                        document.title,
                        document.source_url,
                        document.published_at,
                        text,
                        embedding,
                    ),
                )
                conn.execute(
                    """
                    insert into kb_chunks_fts (
                        chunk_id, document_id, title, source_url, text
                    )
                    values (?, ?, ?, ?, ?)
                    """,
                    (chunk_id, document.document_id, document.title, document.source_url, text),
                )

    async def replace_site_documents(self, *, site_id: str, active_document_ids: list[str]) -> None:
        with self._connect() as conn:
            if active_document_ids:
                placeholders = ",".join("?" for _ in active_document_ids)
                stale_rows = conn.execute(
                    f"""
                    select document_id
                    from kb_documents
                    where site_id = ? and document_id not in ({placeholders})
                    """,
                    (site_id, *active_document_ids),
                ).fetchall()
            else:
                stale_rows = conn.execute(
                    "select document_id from kb_documents where site_id = ?",
                    (site_id,),
                ).fetchall()
            stale_ids = [str(row["document_id"]) for row in stale_rows]
            if not stale_ids:
                return
            stale_placeholders = ",".join("?" for _ in stale_ids)
            conn.execute(
                f"update kb_documents set status = 'inactive', updated_at = datetime('now') where document_id in ({stale_placeholders})",
                tuple(stale_ids),
            )
            conn.execute(
                f"delete from kb_chunks where document_id in ({stale_placeholders})",
                tuple(stale_ids),
            )
            conn.execute(
                f"delete from kb_chunks_fts where document_id in ({stale_placeholders})",
                tuple(stale_ids),
            )

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
        query_vector = hash_embedding(query, self.vector_dimensions)
        with self._connect() as conn:
            title = self._title_candidates(conn, query=query, space_id=space_id, limit=max(30, top_k * 8))
            lexical = self._lexical_candidates(conn, query=query, space_id=space_id, limit=max(30, top_k * 8))
            vector = self._vector_candidates(conn, query_vector=query_vector, space_id=space_id, limit=max(30, top_k * 8))
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
            item["score"] = 3.0 * title_score + 0.8 * lexical_score + 0.25 * vector_score
            scored.append(item)
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
        del sort
        if collection not in {"kb_pages", "kb_documents"}:
            return []
        rows = self._list_documents(filters=filters, limit=limit)
        return [project_fields(row, fields) for row in rows]

    async def create_item(self, collection: str, payload: dict[str, Any]) -> dict[str, Any]:
        if collection not in {"kb_answer_logs", "kb_feedback", "dynamic_qa", "kb_crawl_runs"}:
            raise BackendUnavailable(f"本地知识库不支持写入集合：{collection}")
        with self._connect() as conn:
            cursor = conn.execute(
                "insert into kb_events (collection, payload_json, created_at) values (?, ?, datetime('now'))",
                (collection, json.dumps(payload, ensure_ascii=False)),
            )
            return {"id": cursor.lastrowid, **payload}

    async def update_item(self, collection: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if collection != "kb_crawl_runs":
            raise BackendUnavailable(f"本地知识库不支持更新集合：{collection}")
        with self._connect() as conn:
            row = conn.execute("select payload_json from kb_events where id = ?", (item_id,)).fetchone()
            if row is None:
                raise BackendUnavailable(f"本地记录不存在：{collection}/{item_id}")
            data = json.loads(str(row["payload_json"]))
            data.update(payload)
            conn.execute(
                "update kb_events set payload_json = ? where id = ?",
                (json.dumps(data, ensure_ascii=False), item_id),
            )
            return {"id": item_id, **data}

    def _list_documents(self, *, filters: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        clauses = ["status = 'active'"]
        values: list[Any] = []
        normalized = normalize_filter(filters)
        if normalized.get("space_id"):
            clauses.append("space_id = ?")
            values.append(normalized["space_id"])
        if normalized.get("id_in"):
            placeholders = ",".join("?" for _ in normalized["id_in"])
            clauses.append(f"document_id in ({placeholders})")
            values.extend(normalized["id_in"])
        where = " and ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                select document_id as id, document_id, site_id, space_id, source_url as canonical_url,
                       title, published_at, content_hash, status, markdown_path, quality_json
                from kb_documents
                where {where}
                order by title
                limit ?
                """,
                (*values, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def _title_candidates(self, conn: sqlite3.Connection, *, query: str, space_id: str, limit: int) -> list[dict[str, Any]]:
        query_compact = compact_text(query)
        if not query_compact:
            return []
        rows = conn.execute(
            """
            select c.chunk_id, c.document_id, c.title, c.source_url, c.published_at, c.text
            from kb_chunks c
            join kb_documents d on d.document_id = c.document_id
            where c.chunk_index = 0 and d.status = 'active' and (? = '' or d.space_id = ?)
            """,
            (space_id, space_id),
        ).fetchall()
        candidates: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            title = compact_text(str(item["title"]))
            if not title or is_generic_title(title):
                continue
            if title in query_compact:
                item["title_score"] = min(2.0, 0.8 + len(title) / 10)
                candidates.append(item)
        candidates.sort(key=lambda item: item["title_score"], reverse=True)
        return candidates[:limit]

    def _lexical_candidates(self, conn: sqlite3.Connection, *, query: str, space_id: str, limit: int) -> list[dict[str, Any]]:
        fts_query = build_fts_query(query)
        if not fts_query:
            return []
        space_clause = "and d.space_id = ?" if space_id else ""
        params: list[Any] = [fts_query]
        if space_id:
            params.append(space_id)
        params.append(limit)
        rows = conn.execute(
            f"""
            select c.chunk_id, c.document_id, c.title, c.source_url, c.published_at, c.text,
                   max(0.0, -bm25(kb_chunks_fts)) as lexical_score
            from kb_chunks_fts
            join kb_chunks c on c.chunk_id = kb_chunks_fts.chunk_id
            join kb_documents d on d.document_id = c.document_id
            where kb_chunks_fts match ? {space_clause}
            order by bm25(kb_chunks_fts)
            limit ?
            """,
            tuple(params),
        ).fetchall()
        return [dict(row) for row in rows]

    def _vector_candidates(self, conn: sqlite3.Connection, *, query_vector: list[float], space_id: str, limit: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            select c.chunk_id, c.document_id, c.title, c.source_url, c.published_at, c.text, c.embedding_json
            from kb_chunks c
            join kb_documents d on d.document_id = c.document_id
            where d.status = 'active' and (? = '' or d.space_id = ?)
            """,
            (space_id, space_id),
        ).fetchall()
        scored: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["vector_score"] = cosine(query_vector, json.loads(str(item.pop("embedding_json"))))
            scored.append(item)
        scored.sort(key=lambda item: item["vector_score"], reverse=True)
        return scored[:limit]

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
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
                    quality_json text not null,
                    status text not null,
                    updated_at text not null
                );

                create table if not exists kb_chunks (
                    chunk_id text primary key,
                    document_id text not null,
                    chunk_index integer not null,
                    title text not null,
                    source_url text not null,
                    published_at text,
                    text text not null,
                    embedding_json text not null,
                    foreign key(document_id) references kb_documents(document_id)
                );

                create virtual table if not exists kb_chunks_fts using fts5(
                    chunk_id unindexed,
                    document_id unindexed,
                    title,
                    source_url unindexed,
                    text,
                    tokenize = 'unicode61'
                );

                create table if not exists kb_events (
                    id integer primary key autoincrement,
                    collection text not null,
                    payload_json text not null,
                    created_at text not null
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


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


def hash_embedding(text: str, dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    tokens = tokenize(text)
    for token in tokens:
        bucket = stable_hash(token) % dimensions
        sign = 1.0 if stable_hash(f"+{token}") % 2 == 0 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 6) for value in vector]


def tokenize(text: str) -> list[str]:
    return re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+", text.lower())


def stable_hash(text: str) -> int:
    import hashlib

    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def build_fts_query(query: str) -> str:
    terms = extract_keyword_terms(query)
    return " OR ".join(quote_fts_term(term) for term in terms[:8])


def extract_keyword_terms(query: str) -> list[str]:
    text = compact_text(query)
    for generic in (
        "武汉大学人工智能学院",
        "武汉大学",
        "人工智能学院",
        "有哪些信息",
        "有什么信息",
        "在哪里看",
        "有哪些",
        "什么",
        "信息",
        "请问",
    ):
        text = text.replace(generic, " ")
    known_terms = [
        "本科生培养",
        "研究生培养",
        "师资招聘",
        "学科专业",
        "办事流程",
        "常用下载",
        "培养方案",
        "招生资讯",
        "招生咨讯",
    ]
    terms = [term for term in known_terms if term in query]
    terms.extend(term for term in re.split(r"\s+", text) if len(term) >= 2)
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        if term and term not in seen:
            seen.add(term)
            result.append(term)
    return result


def quote_fts_term(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


def compact_text(text: str) -> str:
    return "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", text.lower()))


def is_generic_title(title: str) -> bool:
    return title in {
        "武汉大学人工智能学院",
        "人工智能学院",
        "学院简介",
    }


def normalize_filter(filters: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    clauses = filters.get("_and") if isinstance(filters.get("_and"), list) else []
    for clause in clauses:
        if not isinstance(clause, dict):
            continue
        for key, value in clause.items():
            if isinstance(value, dict) and "_eq" in value:
                normalized[key] = value["_eq"]
    if isinstance(filters.get("space_id"), dict):
        value = filters["space_id"]
        if "_eq" in value:
            normalized["space_id"] = value["_eq"]
    if isinstance(filters.get("id"), dict) and "_in" in filters["id"]:
        normalized["id_in"] = [str(item) for item in filters["id"]["_in"]]
    return normalized


def project_fields(row: dict[str, Any], fields: list[str] | None) -> dict[str, Any]:
    if not fields:
        return row
    return {field: row.get(field) for field in fields if field in row}
