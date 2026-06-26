from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException

from luoying_bot.capabilities.knowledge_base.artifacts import (
    parse_frontmatter,
    parse_markdown_artifact,
)
from luoying_bot.capabilities.knowledge_base.errors import KnowledgeBaseError
from luoying_bot.capabilities.knowledge_base.schemas import (
    CitationResponse,
    DynamicQaRequest,
    KnowledgeAnswerRequest,
    KnowledgeAnswerResponse,
    KnowledgeFeedbackRequest,
    KnowledgeSearchRequest,
)
from luoying_bot.config import settings

if TYPE_CHECKING:
    from luoying_bot.bootstrap import AppContainer


def create_knowledge_base_router(
    *,
    container_provider: Callable[[], "AppContainer"],
    current_user_dependency: Callable[..., Any],
) -> APIRouter:
    router = APIRouter(prefix="/knowledge", tags=["knowledge"])

    @router.post("/answer", response_model=KnowledgeAnswerResponse)
    async def answer(
        req: KnowledgeAnswerRequest,
        user=Depends(current_user_dependency),
    ) -> KnowledgeAnswerResponse:
        try:
            result = await container_provider().services.knowledge_base_service.answer(
                question=req.question,
                space_id=req.space_id,
                platform=req.platform or "web",
                conversation_id=req.conversation_id or "web-knowledge",
                user_id=req.user_id or user.user_id,
                filters=req.filters,
                top_k=req.top_k,
            )
        except KnowledgeBaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _answer_response(result.to_dict())

    @router.post("/search")
    async def search(
        req: KnowledgeSearchRequest,
        user=Depends(current_user_dependency),
    ) -> dict[str, Any]:
        try:
            result = await container_provider().services.knowledge_base_service.search(
                query_text=req.query,
                space_id=req.space_id,
                filters=req.filters,
                top_k=req.top_k,
            )
        except KnowledgeBaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "structured_records": [record.to_dict() for record in result.structured_records],
            "chunks": [chunk.to_dict() for chunk in result.chunks],
            "citations": [citation.to_dict() for citation in result.citations()],
            "fallback_reason": result.fallback_reason,
            "user_id": user.user_id,
        }

    @router.post("/dynamic-qa")
    async def submit_dynamic_qa(
        req: DynamicQaRequest,
        user=Depends(current_user_dependency),
    ) -> dict[str, Any]:
        try:
            result = await container_provider().services.knowledge_base_service.submit_dynamic_qa(
                question=req.question,
                answer=req.answer,
                space_id=req.space_id,
                submitted_by=req.submitted_by or user.user_id,
                source_platform=req.source_platform or "web",
                source_conversation_id=req.source_conversation_id or "",
                source_message_id=req.source_message_id or "",
                metadata=req.metadata,
            )
        except KnowledgeBaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": result}

    @router.post("/feedback")
    async def submit_feedback(
        req: KnowledgeFeedbackRequest,
        user=Depends(current_user_dependency),
    ) -> dict[str, Any]:
        try:
            result = await container_provider().services.knowledge_base_service.submit_feedback(
                feedback_type=req.feedback_type,
                answer_log_id=req.answer_log_id,
                request_uid=req.request_uid,
                comment=req.comment,
                submitted_by=req.submitted_by or user.user_id,
            )
        except KnowledgeBaseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": result}

    @router.get("/admin/sources")
    async def list_sources(
        user=Depends(current_user_dependency),
    ) -> dict[str, Any]:
        del user
        root = settings.kb_artifact_root / "sources"
        sources = []
        if root.exists():
            for source_dir in sorted(path for path in root.iterdir() if path.is_dir()):
                manifest = _read_source_manifest(source_dir)
                pages = list((source_dir / "pages").glob("*.md"))
                raw_files = list((source_dir / "raw").glob("*"))
                graph_path = source_dir / "graph.jsonl"
                sources.append(
                    {
                        "site_id": source_dir.name,
                        "name": manifest.get("name") or source_dir.name,
                        "base_url": manifest.get("base_url"),
                        "space_id": manifest.get("space_id"),
                        "updated_at": manifest.get("updated_at"),
                        "max_pages": manifest.get("max_pages"),
                        "max_depth": manifest.get("max_depth"),
                        "page_count": len(pages),
                        "raw_count": len(raw_files),
                        "edge_count": _count_jsonl(graph_path),
                        "manifest": manifest,
                    }
                )
        return {"sources": sources}

    @router.get("/admin/sources/{site_id}/tree")
    async def source_tree(
        site_id: str,
        user=Depends(current_user_dependency),
    ) -> dict[str, Any]:
        del user
        source_dir = _resolve_source_dir(site_id)
        documents = _read_source_documents(source_dir)
        edges = _read_graph(source_dir / "graph.jsonl")
        return {
            "site_id": source_dir.name,
            "manifest": _read_source_manifest(source_dir),
            "tree": _build_url_tree(documents),
            "documents": documents,
            "edges": edges,
        }

    @router.get("/admin/sources/{site_id}/pages/{document_id}")
    async def page_detail(
        site_id: str,
        document_id: str,
        user=Depends(current_user_dependency),
    ) -> dict[str, Any]:
        del user
        source_dir = _resolve_source_dir(site_id)
        document_path = _resolve_page_path(source_dir, document_id)
        metadata, body = parse_markdown_artifact(document_path.read_text(encoding="utf-8"))
        edges = _read_graph(source_dir / "graph.jsonl")
        url = str(metadata.get("url") or "")
        outgoing = [edge for edge in edges if edge.get("from_id") == document_id or edge.get("from") == url]
        incoming = [edge for edge in edges if edge.get("to_id") == document_id or edge.get("to") == url]
        raw_path = _safe_relative_file(source_dir, str(metadata.get("raw_path") or ""))
        raw_exists = raw_path.exists() if raw_path is not None else False
        return {
            "site_id": source_dir.name,
            "document_id": document_id,
            "metadata": metadata,
            "markdown": body,
            "markdown_path": document_path.relative_to(settings.kb_artifact_root).as_posix(),
            "raw_exists": raw_exists,
            "outgoing": outgoing,
            "incoming": incoming,
        }

    return router


def _answer_response(data: dict[str, Any]) -> KnowledgeAnswerResponse:
    return KnowledgeAnswerResponse(
        answer=str(data.get("answer") or ""),
        citations=[
            CitationResponse(**citation)
            for citation in data.get("citations", [])
            if isinstance(citation, dict)
        ],
        confidence=float(data.get("confidence") or 0.0),
        need_follow_up=bool(data.get("need_follow_up")),
        follow_up_question=data.get("follow_up_question"),
        image_url=data.get("image_url"),
        fallback_reason=data.get("fallback_reason"),
        data=dict(data.get("data") or {}),
    )


def _resolve_source_dir(site_id: str) -> Path:
    if not site_id or Path(site_id).name != site_id or site_id in {".", ".."}:
        raise HTTPException(status_code=400, detail="知识源标识无效")
    source_dir = (settings.kb_artifact_root / "sources" / site_id).resolve()
    sources_root = (settings.kb_artifact_root / "sources").resolve()
    if sources_root != source_dir.parent or not source_dir.exists() or not source_dir.is_dir():
        raise HTTPException(status_code=404, detail="知识源不存在")
    return source_dir


def _resolve_page_path(source_dir: Path, document_id: str) -> Path:
    if not document_id or Path(document_id).name != document_id or document_id in {".", ".."}:
        raise HTTPException(status_code=400, detail="页面标识无效")
    page_path = (source_dir / "pages" / f"{document_id}.md").resolve()
    pages_dir = (source_dir / "pages").resolve()
    if pages_dir != page_path.parent or not page_path.exists() or not page_path.is_file():
        raise HTTPException(status_code=404, detail="页面不存在")
    return page_path


def _safe_relative_file(base: Path, relative_path: str) -> Path | None:
    if not relative_path or relative_path.startswith("/"):
        return None
    target = (base / relative_path).resolve()
    resolved_base = base.resolve()
    if resolved_base != target and resolved_base not in target.parents:
        return None
    return target


def _read_source_manifest(source_dir: Path) -> dict[str, Any]:
    path = source_dir / "source.yaml"
    if not path.exists():
        return {}
    return parse_frontmatter(path.read_text(encoding="utf-8"))


def _read_source_documents(source_dir: Path) -> list[dict[str, Any]]:
    documents = []
    for path in sorted((source_dir / "pages").glob("*.md")):
        try:
            metadata, body = parse_markdown_artifact(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        url = str(metadata.get("url") or "")
        documents.append(
            {
                "id": metadata.get("id") or path.stem,
                "title": metadata.get("title") or path.stem,
                "url": url,
                "path": urlparse(url).path or "/",
                "space_id": metadata.get("space_id"),
                "content_type": metadata.get("content_type"),
                "published_at": metadata.get("published_at"),
                "fetched_at": metadata.get("fetched_at"),
                "depth": metadata.get("depth"),
                "link_count": metadata.get("link_count"),
                "quality": metadata.get("quality") or {},
                "chars": len(body),
            }
        )
    return documents


def _read_graph(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    edges = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            edges.append(item)
    return edges


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _build_url_tree(documents: list[dict[str, Any]]) -> dict[str, Any]:
    root = {"name": "/", "path": "/", "children": [], "documents": []}
    for document in documents:
        raw_path = str(document.get("path") or "/").strip("/")
        parts = [part for part in raw_path.split("/") if part]
        if not parts:
            root["documents"].append(document)
            continue
        current = root
        accumulated = ""
        for part in parts[:-1]:
            accumulated = f"{accumulated}/{part}"
            child = _find_child(current, part)
            if child is None:
                child = {"name": part, "path": accumulated, "children": [], "documents": []}
                current["children"].append(child)
            current = child
        current["documents"].append(document)
    _sort_tree(root)
    return root


def _find_child(node: dict[str, Any], name: str) -> dict[str, Any] | None:
    for child in node["children"]:
        if child["name"] == name:
            return child
    return None


def _sort_tree(node: dict[str, Any]) -> None:
    node["children"].sort(key=lambda item: str(item["name"]))
    node["documents"].sort(key=lambda item: str(item.get("path") or item.get("title") or ""))
    for child in node["children"]:
        _sort_tree(child)
