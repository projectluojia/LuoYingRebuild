from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse

DEFAULT_EXCLUDED_SELECTOR = ", ".join(
    [
        "header",
        "nav",
        "footer",
        ".footer",
        ".pc_h",
        "#m_n_nav",
        ".nLeft",
        ".mianbao",
        ".nav_mask",
        ".search",
        ".logo",
        ".top",
        ".topbar",
    ]
)


@dataclass(slots=True)
class ExtractedContent:
    url: str
    title: str
    markdown: str
    raw_html: str
    links: list[dict[str, Any]]
    published_at: str | None = None
    content_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class Crawl4AIExtractor:
    async def __aenter__(self) -> "Crawl4AIExtractor":
        os.environ.setdefault(
            "CRAWL4_AI_BASE_DIRECTORY",
            str((Path.cwd() / "var" / "crawl4ai").resolve()),
        )
        os.environ.setdefault(
            "PLAYWRIGHT_BROWSERS_PATH",
            str((Path.cwd() / "var" / "playwright").resolve()),
        )
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
        from crawl4ai.content_filter_strategy import PruningContentFilter
        from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

        self._crawler = AsyncWebCrawler()
        self._home_run_config = CrawlerRunConfig(
            markdown_generator=DefaultMarkdownGenerator(
                content_filter=PruningContentFilter(
                    threshold=0.48,
                    threshold_type="fixed",
                ),
                options={"ignore_links": False},
            ),
            excluded_tags=["script", "style", "noscript", "header", "nav", "footer"],
            excluded_selector=DEFAULT_EXCLUDED_SELECTOR,
            remove_forms=True,
            remove_overlay_elements=True,
            word_count_threshold=2,
            verbose=False,
        )
        self._inner_run_config = CrawlerRunConfig(
            markdown_generator=DefaultMarkdownGenerator(
                options={"ignore_links": False},
            ),
            css_selector=".nRight",
            excluded_tags=["script", "style", "noscript"],
            remove_forms=False,
            word_count_threshold=1,
            verbose=False,
        )
        await self._crawler.__aenter__()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self._crawler.__aexit__(exc_type, exc, tb)

    async def extract(self, *, url: str) -> ExtractedContent:
        result = await self._crawler.arun(url=url, config=self._run_config_for(url))
        if not bool(getattr(result, "success", True)):
            error = getattr(result, "error_message", None) or "Crawl4AI failed"
            raise ValueError(str(error))

        raw_markdown = coerce_markdown(getattr(result, "markdown", ""))
        markdown = normalize_markdown(raw_markdown)
        if not markdown:
            raise ValueError("Crawl4AI extracted empty markdown")

        raw_html = str(getattr(result, "html", "") or "")
        if not raw_html:
            raise ValueError("Crawl4AI did not return raw HTML")

        metadata = coerce_metadata(getattr(result, "metadata", {}))
        title = normalize_title(
            str(metadata.get("title") or ""),
            markdown=markdown,
        )
        published_at = normalize_date(
            str(
                metadata.get("published_at")
                or metadata.get("date")
                or metadata.get("PubDate")
                or metadata.get("pubdate")
                or metadata.get("article:published_time")
                or ""
            )
        ) or infer_published_at(raw_markdown)
        clean_url = normalize_url(str(getattr(result, "url", None) or url))
        return ExtractedContent(
            url=clean_url,
            title=title,
            markdown=markdown,
            raw_html=raw_html,
            links=coerce_links(getattr(result, "links", []), base_url=clean_url),
            published_at=published_at,
            content_hash=sha256_text(markdown),
            metadata=metadata,
        )

    def _run_config_for(self, url: str) -> object:
        parsed = urlparse(normalize_url(url))
        path = parsed.path.strip("/")
        if not path or path == "index.htm":
            return self._home_run_config
        return self._inner_run_config


def coerce_markdown(value: Any) -> str:
    if isinstance(value, str):
        return value
    for attr in ("fit_markdown", "raw_markdown", "markdown"):
        candidate = getattr(value, attr, None)
        if candidate:
            return str(candidate)
    return str(value or "")


def coerce_links(value: Any, *, base_url: str) -> list[dict[str, Any]]:
    items: list[Any]
    if isinstance(value, dict):
        items = []
        for group in ("internal", "external"):
            group_value = value.get(group)
            if isinstance(group_value, list):
                items.extend(group_value)
    elif isinstance(value, list):
        items = value
    else:
        items = []

    links: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, dict):
            href = str(item.get("href") or item.get("url") or "")
            text = str(item.get("text") or item.get("title") or "")
        else:
            href = str(getattr(item, "href", None) or getattr(item, "url", None) or "")
            text = str(getattr(item, "text", None) or getattr(item, "title", None) or "")
        if not href:
            continue
        link_url = normalize_url(urljoin(base_url, href))
        if not link_url or link_url in seen:
            continue
        seen.add(link_url)
        links.append(
            {
                "url": link_url,
                "text": normalize_space(text),
                "is_asset": is_asset_url(link_url),
            }
        )
    return links


def coerce_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            str(key): val
            for key, val in value.items()
            if val is not None and val != ""
        }
    return {}


def normalize_markdown(text: str) -> str:
    lines: list[str] = []
    blank = False
    first_heading_seen = False
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.rstrip()
        stripped = normalize_space(line)
        if not stripped:
            if not blank and lines:
                lines.append("")
            blank = True
            continue
        if is_noise_line(stripped):
            continue
        if stripped.startswith("!["):
            continue
        heading = normalize_heading(line)
        if heading:
            if is_noise_line(heading):
                continue
            if not first_heading_seen:
                line = f"# {heading}"
                first_heading_seen = True
            else:
                line = f"## {heading}"
        else:
            line = normalize_list_heading(line)
            line = clean_markdown_noise(line)
        lines.append(line)
        blank = False
    return "\n".join(lines).strip()


def normalize_url(url: str) -> str:
    clean, _ = urldefrag(url.strip())
    return clean


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_date(value: str) -> str | None:
    text = normalize_space(value)
    if not text or text == "未知":
        return None
    match = re.search(r"(20\d{2})[-./年](\d{1,2})[-./月](\d{1,2})", text)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def infer_published_at(text: str) -> str | None:
    match = re.search(r"发布时间[:：]\s*(20\d{2}[-./年]\d{1,2}[-./月]\d{1,2})", text)
    return normalize_date(match.group(1)) if match else None


def normalize_title(value: str, *, markdown: str) -> str:
    markdown_title = infer_title_from_markdown(markdown)
    title = normalize_space(value)
    if title and markdown_title and markdown_title in title:
        return markdown_title
    return title or markdown_title


def infer_title_from_markdown(markdown: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()[:120]
        if stripped:
            return stripped[:120]
    return "未命名文档"


def normalize_heading(line: str) -> str | None:
    match = re.match(r"^\s*#{1,6}\s+(.+?)\s*$", line)
    if not match:
        return None
    return normalize_space(match.group(1).strip())


def normalize_list_heading(line: str) -> str:
    return re.sub(r"^(\s*[*-]\s+)#{1,6}\s+", r"\1", line)


def clean_markdown_noise(line: str) -> str:
    line = re.sub(r"(\[\s*)__+", r"\1", line)
    line = re.sub(r"\s+\]", " ]", line)
    return line


def is_noise_line(line: str) -> bool:
    if line.startswith(("上一条：", "下一条：", "上一篇：", "下一篇：")):
        return True
    if line.startswith("发布时间：") or line.startswith("发布时间:"):
        return True
    if "发布时间" in line and "点击数" in line:
        return True
    return line in {
        "首页",
        "上页",
        "下页",
        "尾页",
        "TOP",
        "版权所有",
        "您当前位置：",
        "当前位置：",
    }


def is_asset_url(url: str) -> bool:
    path = normalize_url(url).lower()
    return any(
        path.endswith(suffix)
        for suffix in (
            ".pdf",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".zip",
            ".rar",
            ".7z",
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
        )
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
