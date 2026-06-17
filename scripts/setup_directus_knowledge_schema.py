from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from luoying_bot.capabilities.knowledge_base.directus_client import DirectusClient
from luoying_bot.config import settings


async def main() -> None:
    parser = argparse.ArgumentParser(description="Create Directus collections and fields for LuoYing knowledge base")
    parser.add_argument(
        "--schema",
        default="docs/directus/knowledge_base_schema.json",
        help="Path to Directus schema JSON",
    )
    args = parser.parse_args()

    schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    client = DirectusClient(base_url=settings.directus_url, token=settings.directus_token)
    existing_collections = await client.list_collections()
    created_collections: list[str] = []
    created_fields: list[str] = []

    for collection in schema["collections"]:
        name = collection["collection"]
        if name not in existing_collections:
            await client.create_collection(name, note=collection.get("note", ""))
            created_collections.append(name)

        existing_fields = await client.list_fields(name)
        for field in collection.get("fields", []):
            field_name = field["field"]
            if field_name in existing_fields:
                continue
            await client.create_field(
                name,
                field_name,
                field_type=field["type"],
                note=field.get("note", ""),
                required=bool(field.get("required", False)),
                default_value=field.get("default_value"),
            )
            created_fields.append(f"{name}.{field_name}")

    print(
        json.dumps(
            {
                "ok": True,
                "created_collections": created_collections,
                "created_fields": created_fields,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())

