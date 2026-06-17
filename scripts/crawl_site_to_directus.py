from __future__ import annotations

import argparse
import asyncio
import json

from luoying_bot.capabilities.knowledge_base.crawling import (
    DirectusCrawlRecorder,
    KnowledgeSiteCrawler,
    SiteCrawlConfig,
)
from luoying_bot.capabilities.knowledge_base.directus_client import DirectusClient
from luoying_bot.capabilities.knowledge_base.ragflow_client import RagflowClient
from luoying_bot.config import settings


async def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl a Directus-managed site into the knowledge base")
    parser.add_argument("--site-id", required=True, help="kb_sites.site_id")
    args = parser.parse_args()

    directus = DirectusClient(
        base_url=settings.directus_url,
        token=settings.directus_token,
    )
    sites = await directus.list_items(
        "kb_sites",
        filters={"site_id": {"_eq": args.site_id}, "enabled": {"_eq": True}},
        limit=1,
    )
    if not sites:
        raise RuntimeError(f"未找到启用的站点配置：{args.site_id}")

    config = SiteCrawlConfig.from_site_record(sites[0])
    if config.sync_to_ragflow and not config.ragflow_dataset_id:
        config.ragflow_dataset_id = settings.ragflow_default_dataset_id
    if config.sync_to_ragflow and not config.ragflow_dataset_id:
        raise RuntimeError("sync_to_ragflow=true 时必须配置 ragflow_dataset_id 或 RAGFLOW_DEFAULT_DATASET_ID")

    result = await KnowledgeSiteCrawler().crawl(config)
    recorder = DirectusCrawlRecorder(
        directus,
        RagflowClient(
            base_url=settings.ragflow_url,
            api_key=settings.ragflow_api_key,
        ) if config.sync_to_ragflow else None,
    )
    run = await recorder.record(config, result)
    print(
        json.dumps(
            {
                "ok": True,
                "run": run,
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
