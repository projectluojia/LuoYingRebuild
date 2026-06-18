from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass(slots=True)
class KnowledgeArtifact:
    document_id: str
    markdown_path: Path
    raw_html_path: Path
    markdown: str
    metadata: dict[str, Any]


class MarkdownArtifactStore:
    def __init__(self, root: Path):
        self.root = root

    def write_source(self, manifest: dict[str, Any]) -> Path:
        source_dir = self._source_dir(str(manifest["site_id"]))
        source_dir.mkdir(parents=True, exist_ok=True)
        path = source_dir / "source.yaml"
        path.write_text(to_frontmatter_body(manifest), encoding="utf-8")
        return path

    def write_graph(self, *, site_id: str, edges: list[dict[str, Any]]) -> Path:
        source_dir = self._source_dir(site_id)
        source_dir.mkdir(parents=True, exist_ok=True)
        path = source_dir / "graph.jsonl"
        unique: dict[str, dict[str, Any]] = {}
        for edge in edges:
            key = json.dumps(
                {
                    "from": edge.get("from"),
                    "to": edge.get("to"),
                    "type": edge.get("type"),
                    "text": edge.get("text"),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            unique[key] = edge
        lines = [json.dumps(edge, ensure_ascii=False, sort_keys=True) for edge in unique.values()]
        path.write_text("\n".join(lines).strip() + ("\n" if lines else ""), encoding="utf-8")
        return path

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
        depth: int,
        links: list[dict[str, Any]],
    ) -> KnowledgeArtifact:
        document_id = stable_document_id(url)
        source_dir = self._source_dir(site_id)
        pages_dir = source_dir / "pages"
        raw_dir = source_dir / "raw"
        pages_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_html_path = raw_dir / f"{document_id}.html"
        markdown_path = pages_dir / f"{document_id}.md"
        content_hash = sha256_text(normalize_markdown_body(markdown_body))
        metadata = {
            "id": document_id,
            "site_id": site_id,
            "space_id": space_id,
            "title": title,
            "url": url,
            "published_at": published_at,
            "content_hash": content_hash,
            "content_type": infer_content_type(url, markdown_body),
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "depth": depth,
            "link_count": len(links),
            "raw_path": raw_html_path.relative_to(source_dir).as_posix(),
            "quality": quality,
        }
        markdown = build_markdown_document(metadata=metadata, body=markdown_body)
        raw_html_path.write_text(raw_html, encoding="utf-8")
        markdown_path.write_text(markdown, encoding="utf-8")
        return KnowledgeArtifact(
            document_id=document_id,
            markdown_path=markdown_path,
            raw_html_path=raw_html_path,
            markdown=markdown,
            metadata=metadata,
        )

    def graph_edges_for_page(
        self,
        *,
        site_id: str,
        from_url: str,
        from_document_id: str,
        links: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        for link in links:
            to_url = str(link.get("url") or "")
            if not to_url:
                continue
            edges.append(
                {
                    "from": from_url,
                    "from_id": from_document_id,
                    "to": to_url,
                    "to_id": stable_document_id(to_url) if not link.get("is_asset") else None,
                    "site_id": site_id,
                    "type": "asset_link" if link.get("is_asset") else "content_link",
                    "text": str(link.get("text") or ""),
                }
            )
        return edges

    def _source_dir(self, site_id: str) -> Path:
        return self.root / "sources" / safe_path_part(site_id)


def build_markdown_document(*, metadata: dict[str, Any], body: str) -> str:
    frontmatter = ["---"]
    for key, value in metadata.items():
        frontmatter.append(f"{key}: {yaml_scalar(value)}")
    frontmatter.extend(["---", ""])
    clean_body = normalize_markdown_body(body)
    if not clean_body.startswith("# "):
        title = str(metadata.get("title") or "未命名文档")
        clean_body = f"# {title.strip() or '未命名文档'}\n\n{clean_body}".strip()
    return "\n".join(frontmatter + [clean_body, ""]).strip() + "\n"


def parse_markdown_artifact(text: str) -> tuple[dict[str, Any], str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---\n"):
        raise ValueError("Markdown artifact must start with frontmatter")
    end = normalized.find("\n---\n", 4)
    if end < 0:
        raise ValueError("Markdown artifact frontmatter is not closed")
    metadata = parse_frontmatter(normalized[4:end])
    body = normalized[end + len("\n---\n") :].strip()
    return metadata, body


def parse_frontmatter(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"Invalid frontmatter line: {line}")
        value = value.strip()
        data[key.strip()] = json.loads(value) if value else None
    return data


def to_frontmatter_body(data: dict[str, Any]) -> str:
    return "\n".join(f"{key}: {yaml_scalar(value)}" for key, value in data.items()) + "\n"


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


def infer_content_type(url: str, markdown: str) -> str:
    path = urlparse(url).path
    if "/info/" in path:
        return "article"
    if len(re.findall(r"\n\s*[-*]\s+", markdown)) >= 3:
        return "listing"
    return "page"


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


def yaml_scalar(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def portable_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)
