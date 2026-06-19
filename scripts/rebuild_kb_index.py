from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from luoying_bot.capabilities.knowledge_base.artifacts import parse_markdown_artifact
from luoying_bot.capabilities.knowledge_base.embeddings import OpenAICompatibleEmbeddingProvider
from luoying_bot.capabilities.knowledge_base.postgres_store import IndexedDocument, PostgresKnowledgeStore
from luoying_bot.config import settings


async def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild KB Postgres metadata and hybrid index from Markdown artifacts")
    parser.add_argument("--artifact-root", default=str(settings.kb_artifact_root))
    args = parser.parse_args()

    root = Path(args.artifact_root)
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
    count = 0
    for markdown_path in sorted(root.glob("sources/*/pages/*.md")):
        markdown = markdown_path.read_text(encoding="utf-8")
        metadata, body = parse_markdown_artifact(markdown)
        source_dir = markdown_path.parents[1]
        raw_html_path = source_dir / str(metadata["raw_path"])
        await store.upsert_document(
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
            )
        )
        count += 1
    print(
        json.dumps(
            {
                "ok": True,
                "documents_indexed": count,
                "artifact_root": str(root),
                "database_url": settings.kb_database_url,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
