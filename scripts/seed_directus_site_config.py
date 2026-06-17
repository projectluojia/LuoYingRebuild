from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from luoying_bot.capabilities.knowledge_base.crawling import SiteCrawlConfig
from luoying_bot.capabilities.knowledge_base.directus_client import DirectusClient
from luoying_bot.config import settings


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed or update a Directus-managed knowledge site")
    parser.add_argument("--config", required=True, help="Path to site crawl JSON config")
    args = parser.parse_args()

    config = SiteCrawlConfig.from_dict(json.loads(Path(args.config).read_text(encoding="utf-8")))
    client = DirectusClient(base_url=settings.directus_url, token=settings.directus_token)
    existing = await client.list_items(
        "kb_sites",
        filters={"site_id": {"_eq": config.site_id}},
        limit=1,
    )
    payload = config.to_site_record()
    if existing:
        site = await client.update_item("kb_sites", str(existing[0]["id"]), payload)
        action = "updated"
    else:
        site = await client.create_item("kb_sites", payload)
        action = "created"

    print(
        json.dumps(
            {
                "ok": True,
                "action": action,
                "site": site,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
