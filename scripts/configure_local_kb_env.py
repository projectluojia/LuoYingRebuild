from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Update LuoYing .env with local KB service endpoints")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--directus-url", default=None)
    parser.add_argument("--directus-token", default=None)
    parser.add_argument("--ragflow-url", default=None)
    parser.add_argument("--ragflow-api-key", default=None)
    parser.add_argument("--ragflow-dataset-id", default=None)
    args = parser.parse_args()

    updates = {
        "DIRECTUS_URL": args.directus_url,
        "DIRECTUS_TOKEN": args.directus_token,
        "RAGFLOW_URL": args.ragflow_url,
        "RAGFLOW_API_KEY": args.ragflow_api_key,
        "RAGFLOW_DEFAULT_DATASET_ID": args.ragflow_dataset_id,
        "RAGFLOW_SEARCH_PATH": "/api/v1/retrieval" if args.ragflow_url else None,
        "KB_DEFAULT_SPACE_ID": "sai" if args.directus_url or args.ragflow_url else None,
        "KB_DEFAULT_DOMAIN": "admissions" if args.directus_url or args.ragflow_url else None,
        "KB_REQUIRE_CITATION": "true" if args.directus_url or args.ragflow_url else None,
    }
    updates = {key: value for key, value in updates.items() if value is not None}
    if not updates:
        return

    env_path = Path(args.env_file)
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0] if "=" in line and not line.lstrip().startswith("#") else None
        if key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(line)
    missing = [key for key in updates if key not in seen]
    if missing and output and output[-1] != "":
        output.append("")
    output.extend(f"{key}={updates[key]}" for key in missing)
    env_path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
