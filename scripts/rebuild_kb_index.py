from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from luoying_bot.capabilities.knowledge_base.artifacts import build_markdown_document, parse_markdown_artifact, stable_document_id
from luoying_bot.capabilities.knowledge_base.embeddings import OpenAICompatibleEmbeddingProvider
from luoying_bot.capabilities.knowledge_base.postgres_store import IndexedDocument, IndexedDocumentLink, PostgresKnowledgeStore
from luoying_bot.capabilities.knowledge_base.rerankers import LlmReranker
from luoying_bot.capabilities.knowledge_base.structure import (
    document_retrieval_aliases,
    extract_link_structure_texts,
    retrieval_alias_text,
)
from luoying_bot.config import settings
from luoying_bot.infra.llm.openai_chat import OpenAICompatibleChatModel


ArtifactDocument = tuple[Path, dict[str, object], str, Path]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild KB Postgres metadata and hybrid index from Markdown artifacts")
    parser.add_argument("--artifact-root", default=str(settings.kb_artifact_root))
    parser.add_argument(
        "--sync-artifacts-only",
        action="store_true",
        help="Update derived structure metadata in Markdown artifacts without rebuilding Postgres indexes",
    )
    args = parser.parse_args()

    root = Path(args.artifact_root)
    documents, inbound_structure, links_by_site = read_artifact_structure(root)
    if args.sync_artifacts_only:
        synced = sync_artifact_retrieval_aliases(documents=documents, inbound_structure=inbound_structure)
        print(
            json.dumps(
                {
                    "ok": True,
                    "documents_synced": synced,
                    "artifact_root": str(root),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    rerank_model = OpenAICompatibleChatModel(
        settings.openai_base_url,
        settings.openai_api_key,
        settings.openai_model,
        0.0,
        settings.openai_enable_thinking,
    )
    store = PostgresKnowledgeStore(
        settings.kb_database_url,
        embedding_provider=OpenAICompatibleEmbeddingProvider(
            base_url=settings.kb_embedding_base_url,
            api_key=settings.kb_embedding_api_key,
            model=settings.kb_embedding_model,
            query_instruction=settings.kb_embedding_query_instruction,
            batch_size=settings.kb_embedding_batch_size,
        ),
        reranker=LlmReranker(
            rerank_model,
            candidate_limit=settings.kb_rerank_candidate_limit,
            max_text_chars=settings.kb_rerank_max_text_chars,
        ),
        embedding_dimensions=settings.kb_embedding_dimensions,
        min_rerank_score=settings.kb_min_rerank_score,
    )
    try:
        await store.ensure_schema()
        count = 0
        indexed_count = 0
        skipped_count = 0
        total = len(documents)
        for markdown_path, metadata, body, raw_html_path in documents:
            alias_text = retrieval_alias_text(artifact_retrieval_aliases(metadata))
            changed = await store.upsert_document(
                IndexedDocument(
                    document_id=str(metadata["id"]),
                    space_id=str(metadata["space_id"]),
                    site_id=str(metadata["site_id"]),
                    title=str(metadata["title"]),
                    source_url=str(metadata["url"]),
                    published_at=metadata.get("published_at"),
                    content_hash=str(metadata["content_hash"]),
                    markdown_path=str(markdown_path),
                    raw_html_path=str(raw_html_path),
                    quality=dict(metadata.get("quality") or {}),
                    markdown=body,
                    alias_text=alias_text,
                )
            )
            count += 1
            if changed:
                indexed_count += 1
            else:
                skipped_count += 1
            if count == 1 or count % 25 == 0 or count == total:
                print(
                    json.dumps(
                        {
                            "progress": count,
                            "total": total,
                            "indexed": indexed_count,
                            "skipped": skipped_count,
                            "current": str(metadata["title"]),
                            "body_chars": len(body),
                        },
                        ensure_ascii=False,
                    ),
                    file=sys.stderr,
                    flush=True,
                )
        link_count = 0
        for site_id, links in sorted(links_by_site.items()):
            link_count += await store.replace_site_document_links(site_id=site_id, links=links)
        print(
            json.dumps(
                {
                    "ok": True,
                    "documents_seen": count,
                    "documents_indexed": indexed_count,
                    "documents_skipped": skipped_count,
                    "document_links_indexed": link_count,
                    "artifact_root": str(root),
                    "database_url": settings.kb_database_url,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        await store.close()


def read_artifact_structure(root: Path) -> tuple[list[ArtifactDocument], dict[str, list[str]], dict[str, list[IndexedDocumentLink]]]:
    links_by_site: dict[str, list[IndexedDocumentLink]] = {}
    documents: list[ArtifactDocument] = []
    inbound_structure: dict[str, list[str]] = {}
    for markdown_path in sorted(root.glob("sources/*/pages/*.md")):
        markdown = markdown_path.read_text(encoding="utf-8")
        metadata, body = parse_markdown_artifact(markdown)
        source_dir = markdown_path.parents[1]
        raw_html_path = source_dir / str(metadata["raw_path"])
        documents.append((markdown_path, metadata, body, raw_html_path))
        if raw_html_path.exists():
            for target_url, phrases in extract_link_structure_texts(
                html=raw_html_path.read_text(encoding="utf-8", errors="ignore"),
                base_url=str(metadata["url"]),
            ).items():
                inbound_structure.setdefault(stable_document_id(target_url), []).extend(phrases)

    for graph_path in sorted(root.glob("sources/*/graph.jsonl")):
        for link in read_graph_links(graph_path):
            links_by_site.setdefault(link.site_id, []).append(link)
            inbound_structure.setdefault(link.to_document_id, []).append(link.link_text)

    return documents, inbound_structure, links_by_site


def sync_artifact_retrieval_aliases(
    *,
    documents: list[ArtifactDocument],
    inbound_structure: dict[str, list[str]],
) -> int:
    count = 0
    for markdown_path, metadata, body, _raw_html_path in documents:
        retrieval_aliases = document_retrieval_aliases(
            inbound_phrases=inbound_structure.get(str(metadata["id"]), []),
            excluded_phrases=[str(metadata["title"])],
        )
        sync_markdown_retrieval_aliases(
            markdown_path=markdown_path,
            metadata=metadata,
            body=body,
            retrieval_aliases=retrieval_aliases,
        )
        count += 1
    return count


def artifact_retrieval_aliases(metadata: dict[str, object]) -> list[str]:
    raw_aliases = metadata.get("retrieval_aliases")
    if not isinstance(raw_aliases, list):
        raise ValueError(f"Markdown artifact is missing retrieval_aliases: {metadata.get('id')}")
    return [str(alias) for alias in raw_aliases if str(alias).strip()]


def sync_markdown_retrieval_aliases(
    *,
    markdown_path: Path,
    metadata: dict[str, object],
    body: str,
    retrieval_aliases: list[str],
) -> None:
    if metadata.get("retrieval_aliases") == retrieval_aliases:
        return
    updated = dict(metadata)
    updated["retrieval_aliases"] = retrieval_aliases
    markdown_path.write_text(build_markdown_document(metadata=updated, body=body), encoding="utf-8")


def read_graph_links(path: Path) -> list[IndexedDocumentLink]:
    links: list[IndexedDocumentLink] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        edge = json.loads(raw)
        if not isinstance(edge, dict) or edge.get("type") != "content_link" or not edge.get("to_id"):
            continue
        links.append(
            IndexedDocumentLink(
                site_id=str(edge.get("site_id") or ""),
                from_document_id=str(edge.get("from_id") or ""),
                to_document_id=str(edge.get("to_id") or ""),
                from_url=str(edge.get("from") or ""),
                to_url=str(edge.get("to") or ""),
                link_text=str(edge.get("text") or ""),
                link_type=str(edge.get("type") or "content_link"),
                metadata=edge,
            )
        )
    return links


if __name__ == "__main__":
    asyncio.run(main())
