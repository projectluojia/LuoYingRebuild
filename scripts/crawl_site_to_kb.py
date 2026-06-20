from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from luoying_bot.capabilities.knowledge_base.artifacts import MarkdownArtifactStore
from luoying_bot.capabilities.knowledge_base.crawling import (
    KnowledgeCrawlRecorder,
    KnowledgeSiteCrawler,
    SiteCrawlConfig,
)
from luoying_bot.capabilities.knowledge_base.embeddings import OpenAICompatibleEmbeddingProvider
from luoying_bot.capabilities.knowledge_base.postgres_store import PostgresKnowledgeStore
from luoying_bot.config import settings


async def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl a site into Git-managed Markdown artifacts and the Postgres KB index")
    parser.add_argument("--config", required=True, help="Site config JSON")
    args = parser.parse_args()

    config = SiteCrawlConfig.from_dict(json.loads(Path(args.config).read_text(encoding="utf-8")))
    result = await KnowledgeSiteCrawler().crawl(config)
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
    recorder = KnowledgeCrawlRecorder(
        store=store,
        artifact_store=MarkdownArtifactStore(settings.kb_artifact_root),
    )
    run = await recorder.record(config, result)
    print(
        json.dumps(
            {
                "ok": True,
                "run": run,
                "artifact_root": str(settings.kb_artifact_root),
                "database_url": settings.kb_database_url,
                "pages_seen": result.pages_seen,
                "pages_ok": result.pages_ok,
                "pages_failed": result.pages_failed,
                "assets_seen": result.assets_seen,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
