from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from luoying_bot.capabilities.knowledge_base.local_store import IndexedDocument, LocalKnowledgeStore
from luoying_bot.config import settings


async def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild local KB metadata and hybrid index from Markdown artifacts")
    parser.add_argument("--artifact-root", default=str(settings.kb_artifact_root))
    args = parser.parse_args()

    root = Path(args.artifact_root)
    store = LocalKnowledgeStore(
        settings.kb_metadata_db,
        vector_dimensions=settings.kb_vector_dimensions,
    )
    count = 0
    for metadata_path in sorted(root.glob("sources/*/documents/*/metadata.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        markdown_path = Path(str(metadata["markdown_path"]))
        if not markdown_path.is_absolute():
            markdown_path = Path.cwd() / markdown_path
        markdown = markdown_path.read_text(encoding="utf-8")
        await store.upsert_document(
            IndexedDocument(
                document_id=str(metadata["document_id"]),
                space_id=str(metadata["space_id"]),
                site_id=str(metadata["site_id"]),
                title=str(metadata["title"]),
                source_url=str(metadata["source_url"]),
                published_at=metadata.get("published_at"),
                content_hash=str(metadata["content_hash"]),
                markdown_path=str(markdown_path),
                raw_html_path=str(metadata["raw_html_path"]),
                quality=dict(metadata.get("quality") or {}),
                markdown=markdown,
            )
        )
        count += 1
    print(
        json.dumps(
            {
                "ok": True,
                "documents_indexed": count,
                "artifact_root": str(root),
                "metadata_db": str(settings.kb_metadata_db),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
