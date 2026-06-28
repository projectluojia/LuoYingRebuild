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
from luoying_bot.capabilities.knowledge_base.rerankers import LlmReranker
from luoying_bot.config import settings
from luoying_bot.infra.llm.openai_chat import OpenAICompatibleChatModel


async def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl a site into Git-managed Markdown artifacts and the Postgres KB index")
    parser.add_argument("--config", required=True, help="Site config JSON")
    args = parser.parse_args()

    config = SiteCrawlConfig.from_dict(json.loads(Path(args.config).read_text(encoding="utf-8")))
    result = await KnowledgeSiteCrawler().crawl(config)
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
