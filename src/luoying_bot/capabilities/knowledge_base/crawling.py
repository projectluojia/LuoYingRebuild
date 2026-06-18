from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

from luoying_bot.capabilities.knowledge_base.artifacts import MarkdownArtifactStore, stable_document_id
from luoying_bot.capabilities.knowledge_base.extraction import (
    Crawl4AIExtractor,
    is_asset_url,
    normalize_url,
)
from luoying_bot.capabilities.knowledge_base.local_store import IndexedDocument, LocalKnowledgeStore
from luoying_bot.capabilities.knowledge_base.quality import MarkdownQualityChecker


@dataclass(slots=True)
class SiteCrawlConfig:
    site_id: str
    name: str
    base_url: str
    space_id: str
    allowed_domains: list[str]
    entry_urls: list[str]
    max_pages: int = 100
    max_depth: int = 2
    include_url_patterns: list[str] = field(default_factory=list)
    exclude_url_patterns: list[str] = field(default_factory=list)
    blocked_page_patterns: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SiteCrawlConfig":
        return cls(
            site_id=str(data["site_id"]),
            name=str(data.get("name") or data["site_id"]),
            base_url=str(data["base_url"]),
            space_id=str(data.get("space_id") or data["site_id"]),
            allowed_domains=[str(x) for x in data.get("allowed_domains", [])],
            entry_urls=[str(x) for x in data.get("entry_urls", [])],
            max_pages=int(data.get("max_pages") or 100),
            max_depth=int(data.get("max_depth") or 2),
            include_url_patterns=[str(x) for x in data.get("include_url_patterns", [])],
            exclude_url_patterns=[str(x) for x in data.get("exclude_url_patterns", [])],
            blocked_page_patterns=[str(x) for x in data.get("blocked_page_patterns", [])],
        )

    @classmethod
    def from_site_record(cls, record: dict[str, Any]) -> "SiteCrawlConfig":
        crawl_config = record.get("crawl_config") if isinstance(record.get("crawl_config"), dict) else {}
        return cls.from_dict(
            {
                **crawl_config,
                "site_id": record["site_id"],
                "name": record.get("name") or record["site_id"],
                "base_url": record["base_url"],
                "space_id": record.get("space_id") or record["site_id"],
                "allowed_domains": record.get("allowed_domains") or [],
                "entry_urls": record.get("entry_urls") or [],
            }
        )

    def to_site_record(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "name": self.name,
            "base_url": self.base_url,
            "space_id": self.space_id,
            "allowed_domains": self.allowed_domains,
            "entry_urls": self.entry_urls,
            "crawl_config": {
                "max_pages": self.max_pages,
                "max_depth": self.max_depth,
                "include_url_patterns": self.include_url_patterns,
                "exclude_url_patterns": self.exclude_url_patterns,
                "blocked_page_patterns": self.blocked_page_patterns,
            },
            "enabled": True,
        }


@dataclass(slots=True)
class ParsedPage:
    url: str
    title: str
    markdown: str
    links: list[dict[str, Any]]
    published_at: str | None = None
    content_hash: str = ""
    raw_html: str = ""


@dataclass(slots=True)
class CrawlPageResult:
    url: str
    status_code: int
    content_type: str
    depth: int
    parsed: ParsedPage | None = None
    error: str | None = None


@dataclass(slots=True)
class CrawlResult:
    site_id: str
    started_at: str
    finished_at: str
    pages_seen: int
    pages_ok: int
    pages_failed: int
    assets_seen: int
    results: list[CrawlPageResult]


class KnowledgeSiteCrawler:
    async def crawl(self, config: SiteCrawlConfig) -> CrawlResult:
        started = now_iso()
        queue: deque[tuple[str, int]] = deque(
            (normalize_url(urljoin(config.base_url, url)), 0)
            for url in config.entry_urls
        )
        seen: set[str] = set()
        results: list[CrawlPageResult] = []
        assets: set[str] = set()

        async with Crawl4AIExtractor() as extractor:
            while queue and len(seen) < config.max_pages:
                url, depth = queue.popleft()
                if url in seen or not self._allowed(url, config):
                    continue
                seen.add(url)
                if is_asset_url(url):
                    assets.add(url)
                    continue
                try:
                    content = await extractor.extract(url=url)
                    parsed = ParsedPage(
                        url=content.url,
                        title=content.title,
                        markdown=content.markdown,
                        links=content.links,
                        published_at=content.published_at,
                        content_hash=content.content_hash,
                        raw_html=content.raw_html,
                    )
                    if self._blocked_page(parsed, config):
                        results.append(
                            CrawlPageResult(
                                url=url,
                                status_code=200,
                                content_type="text/html",
                                depth=depth,
                                error="blocked_page_detected",
                            )
                        )
                        continue
                    results.append(
                        CrawlPageResult(
                            url=url,
                            status_code=200,
                            content_type="text/html",
                            depth=depth,
                            parsed=parsed,
                        )
                    )
                    if depth < config.max_depth:
                        for link in parsed.links:
                            link_url = str(link.get("url") or "")
                            if link.get("is_asset"):
                                assets.add(link_url)
                                continue
                            if link_url not in seen and self._allowed(link_url, config):
                                queue.append((link_url, depth + 1))
                except Exception as exc:
                    results.append(CrawlPageResult(url=url, status_code=0, content_type="", depth=depth, error=f"{type(exc).__name__}: {exc}"))

        finished = now_iso()
        return CrawlResult(
            site_id=config.site_id,
            started_at=started,
            finished_at=finished,
            pages_seen=len(seen),
            pages_ok=sum(
                1
                for item in results
                if item.status_code and item.status_code < 400 and not item.error
            ),
            pages_failed=sum(1 for item in results if item.error or item.status_code >= 400),
            assets_seen=len(assets),
            results=results,
        )

    def _allowed(self, url: str, config: SiteCrawlConfig) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        if parsed.netloc not in set(config.allowed_domains):
            return False
        if config.include_url_patterns and not any(re.search(pattern, url) for pattern in config.include_url_patterns):
            return False
        if any(re.search(pattern, url) for pattern in config.exclude_url_patterns):
            return False
        return True

    def _blocked_page(self, page: ParsedPage, config: SiteCrawlConfig) -> bool:
        if not config.blocked_page_patterns:
            return False
        target = f"{page.title}\n{page.markdown}"
        return any(re.search(pattern, target) for pattern in config.blocked_page_patterns)


class KnowledgeCrawlRecorder:
    def __init__(
        self,
        *,
        store: LocalKnowledgeStore,
        artifact_store: MarkdownArtifactStore,
    ):
        self.store = store
        self.artifact_store = artifact_store
        self.quality_checker = MarkdownQualityChecker()

    async def record(self, config: SiteCrawlConfig, result: CrawlResult) -> dict[str, Any]:
        run = await self.store.create_item(
            "kb_crawl_runs",
            {
                "site_id": config.site_id,
                "status": "completed",
                "started_at": result.started_at,
                "finished_at": result.finished_at,
                "pages_seen": result.pages_seen,
                "pages_created": 0,
                "pages_updated": 0,
                "pages_failed": result.pages_failed,
                "assets_downloaded": result.assets_seen,
            },
        )
        created = 0
        updated = 0
        graph_edges: list[dict[str, Any]] = []
        active_document_ids: list[str] = []
        self.artifact_store.write_source(
            {
                "site_id": config.site_id,
                "name": config.name,
                "base_url": config.base_url,
                "space_id": config.space_id,
                "allowed_domains": config.allowed_domains,
                "entry_urls": config.entry_urls,
                "max_pages": config.max_pages,
                "max_depth": config.max_depth,
                "updated_at": result.finished_at,
            }
        )
        for page_result in result.results:
            if not page_result.parsed:
                continue
            change, edges = await self._upsert_page(
                config,
                page_result.parsed,
                run.get("id"),
                depth=page_result.depth,
            )
            graph_edges.extend(edges)
            active_document_ids.append(stable_document_id(page_result.parsed.url))
            if change == "created":
                created += 1
            elif change == "updated":
                updated += 1
        self.artifact_store.write_graph(site_id=config.site_id, edges=graph_edges)
        await self.store.replace_site_documents(
            site_id=config.site_id,
            active_document_ids=active_document_ids,
        )
        if run.get("id"):
            run = await self.store.update_item(
                "kb_crawl_runs",
                str(run["id"]),
                {"pages_created": created, "pages_updated": updated},
            )
        return run

    async def _upsert_page(
        self,
        config: SiteCrawlConfig,
        page: ParsedPage,
        run_id: Any,
        *,
        depth: int,
    ) -> tuple[str, list[dict[str, Any]]]:
        del run_id
        existing = await self.store.list_items(
            "kb_pages",
            filters={
                "_and": [
                    {"space_id": {"_eq": config.space_id}},
                    {"status": {"_eq": "active"}},
                ]
            },
            fields=["id", "canonical_url", "content_hash"],
            limit=10000,
        )
        current = next((item for item in existing if item.get("canonical_url") == page.url), None)
        quality = self.quality_checker.check(page.markdown).to_dict()
        artifact = self.artifact_store.write_document(
            site_id=config.site_id,
            space_id=config.space_id,
            url=page.url,
            title=page.title,
            published_at=page.published_at,
            markdown_body=page.markdown,
            raw_html=page.raw_html,
            quality=quality,
            depth=depth,
            links=page.links,
        )
        graph_edges = self.artifact_store.graph_edges_for_page(
            site_id=config.site_id,
            from_url=page.url,
            from_document_id=artifact.document_id,
            links=page.links,
        )
        await self.store.upsert_document(
            IndexedDocument(
                document_id=artifact.document_id,
                space_id=config.space_id,
                site_id=config.site_id,
                title=page.title,
                source_url=page.url,
                published_at=page.published_at,
                content_hash=str(artifact.metadata["content_hash"]),
                markdown_path=str(artifact.markdown_path),
                raw_html_path=str(artifact.raw_html_path),
                quality=quality,
                markdown=artifact.markdown,
            )
        )
        if current is None:
            return "created", graph_edges
        if current.get("content_hash") == artifact.metadata["content_hash"]:
            return "unchanged", graph_edges
        return "updated", graph_edges


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
