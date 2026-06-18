from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urldefrag

import trafilatura


DEFAULT_PRUNE_XPATH = [
    "//header",
    "//nav",
    "//footer",
    "//*[contains(@class, 'footer')]",
    "//*[contains(@class, 'pc_h')]",
    "//*[@id='m_n_nav']",
    "//*[contains(@class, 'nLeft')]",
    "//*[contains(@class, 'mianbao')]",
    "//*[contains(@class, 'nav_mask')]",
    "//*[contains(@class, 'search')]",
]


@dataclass(slots=True)
class ExtractedContent:
    url: str
    title: str
    text: str
    published_at: str | None = None
    content_hash: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


class TrafilaturaExtractor:
    def __init__(self, *, prune_xpath: list[str] | None = None):
        self.prune_xpath = prune_xpath if prune_xpath is not None else DEFAULT_PRUNE_XPATH

    def extract(self, *, url: str, html: str) -> ExtractedContent:
        document = trafilatura.bare_extraction(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
            prune_xpath=self.prune_xpath,
        )
        if document is None:
            raise ValueError("Trafilatura failed to extract content")
        data = document.as_dict()
        metadata = _HtmlMetadataParser.extract(html)
        text = normalize_extracted_text(str(data.get("text") or ""))
        if not text:
            raise ValueError("Trafilatura extracted empty content")
        title = normalize_space(
            str(data.get("title") or metadata.get("page_title") or metadata.get("title") or "")
        )
        if not title:
            title = infer_title_from_text(text)
        published_at = normalize_date(
            str(data.get("date") or metadata.get("published_at") or "")
        )
        if published_at is None and "/info/" in url:
            published_at = infer_published_at(text)
        return ExtractedContent(
            url=normalize_url(url),
            title=title,
            text=text,
            published_at=published_at,
            content_hash=sha256_text(text),
            metadata=metadata,
        )


class _HtmlMetadataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self._in_title = False

    @classmethod
    def extract(cls, html: str) -> dict[str, str]:
        parser = cls()
        parser.feed(html)
        result = dict(parser.meta)
        title = normalize_space(" ".join(parser.title_parts))
        if title:
            result["title"] = title
        page_title = (
            result.get("pagetitle")
            or result.get("pageTitle")
            or result.get("columname")
            or result.get("ColumnName")
        )
        if page_title:
            result["page_title"] = normalize_space(page_title)
        return {key: value for key, value in result.items() if value}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        if tag == "title":
            self._in_title = True
            return
        if tag != "meta":
            return
        name = attr.get("name") or attr.get("Name") or attr.get("property") or attr.get("Property")
        content = attr.get("content") or attr.get("Content") or ""
        if name and content:
            self.meta[name] = normalize_space(content)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            text = normalize_space(data)
            if text:
                self.title_parts.append(text)


def normalize_extracted_text(text: str) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = normalize_space(raw_line)
        if not line or line in {"-", "TOP"}:
            continue
        if "_showDynClicks" in line or "_showDynClickBatch" in line:
            continue
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)
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


def infer_title_from_text(text: str) -> str:
    return normalize_space(text.splitlines()[0] if text.splitlines() else text[:80])[:120]


def infer_published_at(text: str) -> str | None:
    return normalize_date(text)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
