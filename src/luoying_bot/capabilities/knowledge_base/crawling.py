from __future__ import annotations

import hashlib
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse

import httpx

from luoying_bot.capabilities.knowledge_base.ports import StructuredBackend

ASSET_SUFFIXES = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".7z", ".png", ".jpg", ".jpeg", ".webp",
}
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; LuoYingKnowledgeBot/1.0; +https://sai.whu.edu.cn/)"


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
    request_timeout_sec: float = 20.0
    user_agent: str = DEFAULT_USER_AGENT
    include_url_patterns: list[str] = field(default_factory=list)
    exclude_url_patterns: list[str] = field(default_factory=list)
    sync_to_ragflow: bool = True
    extract_structured: bool = True

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
            request_timeout_sec=float(data.get("request_timeout_sec") or 20.0),
            user_agent=str(data.get("user_agent") or DEFAULT_USER_AGENT),
            include_url_patterns=[str(x) for x in data.get("include_url_patterns", [])],
            exclude_url_patterns=[str(x) for x in data.get("exclude_url_patterns", [])],
            sync_to_ragflow=bool(data.get("sync_to_ragflow", True)),
            extract_structured=bool(data.get("extract_structured", True)),
        )


@dataclass(slots=True)
class Link:
    text: str
    url: str
    is_asset: bool = False


@dataclass(slots=True)
class ParsedPage:
    url: str
    title: str
    text: str
    links: list[Link]
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


class _HtmlExtractor(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[Link] = []
        self._in_title = False
        self._skip_depth = 0
        self._active_href: str | None = None
        self._active_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: v for k, v in attrs}
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag == "a":
            self._active_href = attr.get("href")
            self._active_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._active_href:
            url = normalize_url(urljoin(self.base_url, self._active_href))
            text = normalize_space(" ".join(self._active_text))
            self.links.append(Link(text=text, url=url, is_asset=is_asset_url(url)))
            self._active_href = None
            self._active_text = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = normalize_space(data)
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        if self._active_href is not None:
            self._active_text.append(text)
        self.text_parts.append(text)


class HttpPageFetcher:
    async def fetch(self, url: str, config: SiteCrawlConfig) -> tuple[int, str, str]:
        headers = {
            "User-Agent": config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        }
        async with httpx.AsyncClient(
            timeout=config.request_timeout_sec,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)
        return response.status_code, response.headers.get("content-type", ""), response.text


class KnowledgeSiteCrawler:
    def __init__(self, fetcher: HttpPageFetcher | None = None):
        self.fetcher = fetcher or HttpPageFetcher()

    async def crawl(self, config: SiteCrawlConfig) -> CrawlResult:
        started = now_iso()
        queue: deque[tuple[str, int]] = deque(
            (normalize_url(urljoin(config.base_url, url)), 0)
            for url in config.entry_urls
        )
        seen: set[str] = set()
        results: list[CrawlPageResult] = []
        assets: set[str] = set()

        while queue and len(seen) < config.max_pages:
            url, depth = queue.popleft()
            if url in seen or not self._allowed(url, config):
                continue
            seen.add(url)
            if is_asset_url(url):
                assets.add(url)
                continue
            try:
                status, content_type, body = await self.fetcher.fetch(url, config)
                parsed = parse_html(url, body) if status < 400 and "html" in content_type.lower() else None
                results.append(CrawlPageResult(url=url, status_code=status, content_type=content_type, depth=depth, parsed=parsed))
                if parsed and depth < config.max_depth:
                    for link in parsed.links:
                        if link.is_asset:
                            assets.add(link.url)
                            continue
                        if link.url not in seen and self._allowed(link.url, config):
                            queue.append((link.url, depth + 1))
            except Exception as exc:
                results.append(CrawlPageResult(url=url, status_code=0, content_type="", depth=depth, error=f"{type(exc).__name__}: {exc}"))

        finished = now_iso()
        return CrawlResult(
            site_id=config.site_id,
            started_at=started,
            finished_at=finished,
            pages_seen=len(seen),
            pages_ok=sum(1 for item in results if item.status_code and item.status_code < 400),
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


class DirectusCrawlRecorder:
    def __init__(self, backend: StructuredBackend):
        self.backend = backend

    async def record(self, config: SiteCrawlConfig, result: CrawlResult) -> dict[str, Any]:
        run = await self.backend.create_item(
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
        for page_result in result.results:
            if not page_result.parsed:
                continue
            change = await self._upsert_page(config, page_result.parsed, run.get("id"))
            if change == "created":
                created += 1
            elif change == "updated":
                updated += 1
        if run.get("id"):
            run = await self.backend.update_item(
                "kb_crawl_runs",
                str(run["id"]),
                {"pages_created": created, "pages_updated": updated},
            )
        return run

    async def _upsert_page(self, config: SiteCrawlConfig, page: ParsedPage, run_id: Any) -> str:
        existing = await self.backend.list_items(
            "kb_pages",
            filters={"canonical_url": {"_eq": page.url}},
            limit=1,
        )
        payload = {
            "site_id": config.site_id,
            "space_id": config.space_id,
            "canonical_url": page.url,
            "title": page.title,
            "published_at": page.published_at,
            "content_hash": page.content_hash,
            "status": "active",
            "ragflow_sync_status": "pending" if config.sync_to_ragflow else "disabled",
            "extract_status": "pending" if config.extract_structured else "disabled",
            "last_crawled_at": now_iso(),
            "last_crawl_run": run_id,
        }
        if existing:
            current = existing[0]
            item_id = str(current["id"])
            if current.get("content_hash") == page.content_hash:
                await self.backend.update_item("kb_pages", item_id, payload)
                return "unchanged"
            await self.backend.update_item("kb_pages", item_id, payload)
            await self._create_version(item_id, page)
            return "updated"
        created = await self.backend.create_item("kb_pages", payload)
        if created.get("id"):
            await self._create_version(str(created["id"]), page)
        return "created"

    async def _create_version(self, page_id: str, page: ParsedPage) -> None:
        await self.backend.create_item(
            "kb_page_versions",
            {
                "page_id": page_id,
                "content_hash": page.content_hash,
                "raw_html": page.raw_html,
                "clean_text": page.text,
                "created_at": now_iso(),
            },
        )


def parse_html(url: str, html: str) -> ParsedPage:
    parser = _HtmlExtractor(url)
    parser.feed(html)
    text = normalize_space("\n".join(parser.text_parts))
    title = normalize_space(" ".join(parser.title_parts)) or infer_title_from_text(text)
    return ParsedPage(
        url=normalize_url(url),
        title=title,
        text=text,
        links=dedupe_links(parser.links),
        published_at=infer_published_at(text),
        content_hash=sha256_text(text),
        raw_html=html,
    )


def dedupe_links(links: list[Link]) -> list[Link]:
    seen: set[str] = set()
    result: list[Link] = []
    for link in links:
        if link.url in seen:
            continue
        seen.add(link.url)
        result.append(link)
    return result


def normalize_url(url: str) -> str:
    clean, _ = urldefrag(url.strip())
    return clean


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def is_asset_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(suffix) for suffix in ASSET_SUFFIXES)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def infer_title_from_text(text: str) -> str:
    return text[:80]


def infer_published_at(text: str) -> str | None:
    match = re.search(r"(20\d{2})[-./年](\d{1,2})[-./月](\d{1,2})", text)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
