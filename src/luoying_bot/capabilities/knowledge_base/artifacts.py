from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass(slots=True)
class KnowledgeArtifact:
    document_id: str
    markdown_path: Path
    raw_html_path: Path
    metadata_path: Path
    markdown: str
    metadata: dict[str, Any]


class MarkdownArtifactStore:
    def __init__(self, root: Path):
        self.root = root

    def write_document(
        self,
        *,
        site_id: str,
        space_id: str,
        url: str,
        title: str,
        published_at: str | None,
        markdown_body: str,
        raw_html: str,
        quality: dict[str, Any],
    ) -> KnowledgeArtifact:
        document_id = stable_document_id(url)
        directory = self.root / "sources" / safe_path_part(site_id) / "documents" / document_id
        directory.mkdir(parents=True, exist_ok=True)
        markdown = build_markdown_document(
            title=title,
            source_url=url,
            published_at=published_at,
            body=markdown_body,
        )
        content_hash = sha256_text(markdown)
        raw_html_path = directory / "raw.html"
        markdown_path = directory / "current.md"
        metadata_path = directory / "metadata.json"
        metadata = {
            "document_id": document_id,
            "site_id": site_id,
            "space_id": space_id,
            "title": title,
            "source_url": url,
            "published_at": published_at,
            "content_hash": content_hash,
            "markdown_path": portable_path(markdown_path),
            "raw_html_path": portable_path(raw_html_path),
            "quality": quality,
        }
        raw_html_path.write_text(raw_html, encoding="utf-8")
        markdown_path.write_text(markdown, encoding="utf-8")
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return KnowledgeArtifact(
            document_id=document_id,
            markdown_path=markdown_path,
            raw_html_path=raw_html_path,
            metadata_path=metadata_path,
            markdown=markdown,
            metadata=metadata,
        )


def build_markdown_document(
    *,
    title: str,
    source_url: str,
    published_at: str | None,
    body: str,
) -> str:
    frontmatter = [
        "---",
        f"title: {yaml_scalar(title)}",
        f"source_url: {yaml_scalar(source_url)}",
        f"published_at: {yaml_scalar(published_at or '')}",
        "---",
        "",
    ]
    clean_body = normalize_markdown_body(body)
    if not clean_body.startswith("# "):
        clean_body = f"# {title.strip() or '未命名文档'}\n\n{clean_body}".strip()
    return "\n".join(frontmatter + [clean_body, ""]).strip() + "\n"


def normalize_markdown_body(text: str) -> str:
    lines: list[str] = []
    blank = False
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.rstrip()
        if is_noise_line(line.strip()):
            continue
        if not line.strip():
            if not blank and lines:
                lines.append("")
            blank = True
            continue
        lines.append(line)
        blank = False
    return "\n".join(lines).strip()


def is_noise_line(line: str) -> bool:
    if not line:
        return False
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


def stable_document_id(url: str) -> str:
    parsed = urlparse(url)
    stem = parsed.path.strip("/").replace("/", "_") or "index"
    stem = re.sub(r"[^0-9A-Za-z._-]+", "_", stem).strip("_") or "document"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"{stem}_{digest}"


def safe_path_part(value: str) -> str:
    clean = re.sub(r"[^0-9A-Za-z._-]+", "_", value.strip())
    return clean.strip("_") or "default"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def yaml_scalar(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def portable_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)
