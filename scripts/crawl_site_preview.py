from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from luoying_bot.capabilities.knowledge_base.crawling import KnowledgeSiteCrawler, SiteCrawlConfig


async def main() -> None:
    parser = argparse.ArgumentParser(description="Preview a knowledge-base site crawl")
    parser.add_argument("--config", required=True, help="Path to site crawl JSON config")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    args = parser.parse_args()

    config = SiteCrawlConfig.from_dict(json.loads(Path(args.config).read_text(encoding="utf-8")))
    result = await KnowledgeSiteCrawler().crawl(config)
    payload = {
        "site_id": result.site_id,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "pages_seen": result.pages_seen,
        "pages_ok": result.pages_ok,
        "pages_failed": result.pages_failed,
        "assets_seen": result.assets_seen,
        "pages": [
            {
                "url": item.url,
                "status_code": item.status_code,
                "content_type": item.content_type,
                "depth": item.depth,
                "error": item.error,
                "title": item.parsed.title if item.parsed else "",
                "published_at": item.parsed.published_at if item.parsed else None,
                "content_hash": item.parsed.content_hash if item.parsed else "",
                "text_preview": item.parsed.text[:240] if item.parsed else "",
                "link_count": len(item.parsed.links) if item.parsed else 0,
            }
            for item in result.results
        ],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    asyncio.run(main())

