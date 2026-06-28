from __future__ import annotations

from typing import Any
from urllib.parse import urldefrag, urljoin

from bs4 import BeautifulSoup
from bs4.element import NavigableString


def extract_link_structure_texts(*, html: str, base_url: str) -> dict[str, list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    links: dict[str, list[str]] = {}
    for anchor in soup.find_all("a", href=True):
        href = normalize_url(urljoin(base_url, str(anchor.get("href") or "")))
        if not href:
            continue
        phrases = link_structure_phrases(anchor)
        if not phrases:
            continue
        bucket = links.setdefault(href, [])
        for phrase in phrases:
            if phrase not in bucket:
                bucket.append(phrase)
    return links


def document_retrieval_aliases(*, inbound_phrases: list[str], excluded_phrases: list[str]) -> list[str]:
    pieces = inbound_phrases
    excluded = {compact_key(phrase) for phrase in excluded_phrases if phrase.strip()}
    seen: set[str] = set()
    aliases: list[str] = []
    for piece in pieces:
        clean = normalize_structure_phrase(piece)
        if not clean:
            continue
        key = compact_key(clean)
        if key in excluded:
            continue
        if key in seen:
            continue
        seen.add(key)
        aliases.append(clean)
    return aliases


def retrieval_alias_text(aliases: list[str]) -> str:
    return "\n".join(alias.strip() for alias in aliases if alias.strip())[:1600]


def link_structure_phrases(anchor: Any) -> list[str]:
    anchor_text = node_text(anchor, max_chars=48)
    phrases = [str(anchor.get("title") or ""), anchor_text]
    for parent in anchor.parents:
        if getattr(parent, "name", None) in STRUCTURE_CONTEXT_TAGS:
            phrases.extend(link_group_phrases(parent))
    return unique_phrases(phrases)


def link_group_phrases(node: Any) -> list[str]:
    labels = unique_phrases([node_text(link, max_chars=48) for link in node.find_all("a", href=True)])
    if len(labels) < 2 or len(labels) > 12:
        return []
    phrase = " ".join(labels)
    return [phrase] if normalize_structure_phrase(phrase) else []


def node_text(node: Any, *, max_chars: int) -> str:
    parts = [
        str(descendant).strip()
        for descendant in node.descendants
        if isinstance(descendant, NavigableString)
        and not any(getattr(parent, "name", None) in IGNORED_TEXT_TAGS for parent in descendant.parents)
    ]
    return normalize_space(" ".join(part for part in parts if part))[:max_chars]


def unique_phrases(phrases: list[str]) -> list[str]:
    clean_phrases: list[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        clean = normalize_structure_phrase(phrase)
        if not clean:
            continue
        key = compact_key(clean)
        if key in seen:
            continue
        seen.add(key)
        clean_phrases.append(clean)
    return clean_phrases


def normalize_url(url: str) -> str:
    clean, _ = urldefrag(url.strip())
    return clean


def normalize_structure_phrase(text: str) -> str:
    clean = normalize_space(text.replace("\xa0", " "))
    if len(clean) < 2 or len(clean) > 96:
        return ""
    if not any(char.isalnum() or "\u4e00" <= char <= "\u9fff" for char in clean):
        return ""
    return clean


def normalize_space(text: str) -> str:
    return " ".join((text or "").split())


def compact_key(text: str) -> str:
    return "".join(char for char in text.lower() if char.isalnum() or "\u4e00" <= char <= "\u9fff")


IGNORED_TEXT_TAGS = ["script", "style", "noscript", "svg"]
STRUCTURE_CONTEXT_TAGS = {"li", "nav", "header", "aside", "section", "ul", "ol", "dl", "div"}
