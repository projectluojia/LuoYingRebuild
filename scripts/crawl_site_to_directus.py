from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from luoying_bot.capabilities.knowledge_base.crawling import (
    DirectusCrawlRecorder,
    KnowledgeSiteCrawler,
    SiteCrawlConfig,
)
from luoying_bot.capabilities.knowledge_base.directus_client import DirectusClient
from luoying_bot.config import settings


async def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl a configured site and write page versions to Directus")
    parser.add_argument("--config", required=True, help="Path to site crawl JSON config")
    args = parser.parse_args()

    config = SiteCrawlConfig.from_dict(json.loads(Path(args.config).read_text(encoding="utf-8")))
    result = await KnowledgeSiteCrawler().crawl(config)
    recorder = DirectusCrawlRecorder(
        DirectusClient(
            base_url=settings.directus_url,
            token=settings.directus_token,
        )
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

