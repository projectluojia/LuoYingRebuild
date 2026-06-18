from __future__ import annotations

import argparse
from pathlib import Path


LOCAL_OVERRIDES = {
    "DEVICE": "cpu",
    "DOC_ENGINE": "elasticsearch",
    "COMPOSE_PROFILES": "elasticsearch,cpu",
    "ES_PORT": "1200",
    "EXPOSE_MYSQL_PORT": "13306",
    "MINIO_PORT": "19000",
    "MINIO_CONSOLE_PORT": "19001",
    "REDIS_PORT": "16379",
    "SVR_WEB_HTTP_PORT": "8088",
    "SVR_WEB_HTTPS_PORT": "8443",
    "SVR_HTTP_PORT": "9380",
    "ADMIN_SVR_HTTP_PORT": "9381",
    "SVR_MCP_PORT": "9382",
    "GO_HTTP_PORT": "9384",
    "GO_ADMIN_PORT": "9383",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply LuoYing local overrides to RAGFlow official .env")
    parser.add_argument("--env-file", default="deploy/kb/ragflow/.env")
    args = parser.parse_args()

    path = Path(args.env_file)
    lines = path.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if key in LOCAL_OVERRIDES:
            output.append(f"{key}={LOCAL_OVERRIDES[key]}")
            seen.add(key)
        else:
            output.append(line)
    missing = [key for key in LOCAL_OVERRIDES if key not in seen]
    if missing:
        output.append("")
        output.append("# LuoYing local deployment overrides")
        output.extend(f"{key}={LOCAL_OVERRIDES[key]}" for key in missing)
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
