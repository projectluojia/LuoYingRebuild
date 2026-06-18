from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EMBEDDING_PROVIDER_ID = "hfprovider000000000000000000001"
EMBEDDING_INSTANCE_ID = "hfinstance000000000000000000001"
EMBEDDING_MODEL_ID = "hfmodel00000000000000000000001"
CHAT_PROVIDER_ID = "oaicprovider000000000000000001"
CHAT_INSTANCE_ID = "oaicinstance000000000000000001"
CHAT_MODEL_ID = "oaicmodel00000000000000000001"


def parse_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip("\"'")
    return result


def update_env(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(line)
    missing = [key for key in updates if key not in seen]
    if missing and output and output[-1] != "":
        output.append("")
    output.extend(f"{key}={updates[key]}" for key in missing)
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def sql_literal(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def normalize_host_url(url: str) -> str:
    return url.replace("host.docker.internal", "127.0.0.1").rstrip("/")


class RagflowMysql:
    def __init__(self, *, container: str, password: str, database: str):
        self.container = container
        self.password = password
        self.database = database

    def execute(self, sql: str) -> str:
        cmd = [
            "docker",
            "exec",
            "-i",
            self.container,
            "mysql",
            "-uroot",
            f"-p{self.password}",
            self.database,
            "-N",
            "-B",
        ]
        result = subprocess.run(
            cmd,
            input=sql,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"RAGFlow MySQL command failed: {message}")
        return result.stdout.strip()

    def scalar(self, sql: str) -> str:
        output = self.execute(sql)
        return output.splitlines()[0].split("\t")[0] if output else ""


def request_json(
    *,
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read().decode("utf-8")
    parsed = json.loads(raw) if raw else {}
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Unexpected JSON response from {url}")
    if parsed.get("code") not in (None, 0):
        raise RuntimeError(f"RAGFlow API failed: {parsed.get('message') or parsed.get('code')}")
    return parsed


def register_embedding(mysql: RagflowMysql, *, tenant_id: str, base_url: str, model: str) -> str:
    now_ms, now_dt = current_times()
    provider_name = "HuggingFace"
    instance_name = "default"
    embedding_id = f"{model}@{instance_name}@{provider_name}"
    extra = json.dumps({"base_url": base_url, "max_tokens": 512}, separators=(",", ":"))
    mysql.execute(
        f"""
        INSERT INTO tenant_model_provider
          (id, create_time, create_date, update_time, update_date, provider_name, tenant_id)
        VALUES
          ({sql_literal(EMBEDDING_PROVIDER_ID)}, {now_ms}, {sql_literal(now_dt)}, {now_ms}, {sql_literal(now_dt)},
           {sql_literal(provider_name)}, {sql_literal(tenant_id)})
        ON DUPLICATE KEY UPDATE
          update_time=VALUES(update_time), update_date=VALUES(update_date),
          provider_name=VALUES(provider_name), tenant_id=VALUES(tenant_id);

        INSERT INTO tenant_model_instance
          (id, create_time, create_date, update_time, update_date, instance_name, provider_id, api_key, status, extra)
        VALUES
          ({sql_literal(EMBEDDING_INSTANCE_ID)}, {now_ms}, {sql_literal(now_dt)}, {now_ms}, {sql_literal(now_dt)},
           {sql_literal(instance_name)}, {sql_literal(EMBEDDING_PROVIDER_ID)}, '', 'active', {sql_literal(extra)})
        ON DUPLICATE KEY UPDATE
          update_time=VALUES(update_time), update_date=VALUES(update_date),
          instance_name=VALUES(instance_name), provider_id=VALUES(provider_id),
          status=VALUES(status), extra=VALUES(extra);

        INSERT INTO tenant_model
          (id, create_time, create_date, update_time, update_date, model_name, provider_id, instance_id, model_type, status, extra)
        VALUES
          ({sql_literal(EMBEDDING_MODEL_ID)}, {now_ms}, {sql_literal(now_dt)}, {now_ms}, {sql_literal(now_dt)},
           {sql_literal(model)}, {sql_literal(EMBEDDING_PROVIDER_ID)}, {sql_literal(EMBEDDING_INSTANCE_ID)},
           'embedding', 'active', {sql_literal(extra)})
        ON DUPLICATE KEY UPDATE
          update_time=VALUES(update_time), update_date=VALUES(update_date),
          model_name=VALUES(model_name), provider_id=VALUES(provider_id),
          instance_id=VALUES(instance_id), model_type=VALUES(model_type),
          status=VALUES(status), extra=VALUES(extra);

        UPDATE tenant
        SET embd_id={sql_literal(embedding_id)}, update_time={now_ms}, update_date={sql_literal(now_dt)}
        WHERE id={sql_literal(tenant_id)};
        """
    )
    return embedding_id


def register_chat(
    mysql: RagflowMysql,
    *,
    tenant_id: str,
    base_url: str,
    api_key: str,
    model: str,
) -> str:
    now_ms, now_dt = current_times()
    provider_name = "OpenAI-API-Compatible"
    instance_name = "default"
    chat_id = f"{model}@{instance_name}@{provider_name}"
    extra = json.dumps({"base_url": base_url, "max_tokens": 4096}, separators=(",", ":"))
    mysql.execute(
        f"""
        INSERT INTO tenant_model_provider
          (id, create_time, create_date, update_time, update_date, provider_name, tenant_id)
        VALUES
          ({sql_literal(CHAT_PROVIDER_ID)}, {now_ms}, {sql_literal(now_dt)}, {now_ms}, {sql_literal(now_dt)},
           {sql_literal(provider_name)}, {sql_literal(tenant_id)})
        ON DUPLICATE KEY UPDATE
          update_time=VALUES(update_time), update_date=VALUES(update_date),
          provider_name=VALUES(provider_name), tenant_id=VALUES(tenant_id);

        INSERT INTO tenant_model_instance
          (id, create_time, create_date, update_time, update_date, instance_name, provider_id, api_key, status, extra)
        VALUES
          ({sql_literal(CHAT_INSTANCE_ID)}, {now_ms}, {sql_literal(now_dt)}, {now_ms}, {sql_literal(now_dt)},
           {sql_literal(instance_name)}, {sql_literal(CHAT_PROVIDER_ID)}, {sql_literal(api_key)}, 'active', {sql_literal(extra)})
        ON DUPLICATE KEY UPDATE
          update_time=VALUES(update_time), update_date=VALUES(update_date),
          instance_name=VALUES(instance_name), provider_id=VALUES(provider_id),
          api_key=VALUES(api_key), status=VALUES(status), extra=VALUES(extra);

        INSERT INTO tenant_model
          (id, create_time, create_date, update_time, update_date, model_name, provider_id, instance_id, model_type, status, extra)
        VALUES
          ({sql_literal(CHAT_MODEL_ID)}, {now_ms}, {sql_literal(now_dt)}, {now_ms}, {sql_literal(now_dt)},
           {sql_literal(model)}, {sql_literal(CHAT_PROVIDER_ID)}, {sql_literal(CHAT_INSTANCE_ID)},
           'chat', 'active', {sql_literal(extra)})
        ON DUPLICATE KEY UPDATE
          update_time=VALUES(update_time), update_date=VALUES(update_date),
          model_name=VALUES(model_name), provider_id=VALUES(provider_id),
          instance_id=VALUES(instance_id), model_type=VALUES(model_type),
          status=VALUES(status), extra=VALUES(extra);

        UPDATE tenant
        SET llm_id={sql_literal(chat_id)}, update_time={now_ms}, update_date={sql_literal(now_dt)}
        WHERE id={sql_literal(tenant_id)};
        """
    )
    return chat_id


def ensure_api_token(mysql: RagflowMysql, *, tenant_id: str, preferred_token: str | None) -> str:
    existing = preferred_token or mysql.scalar(
        f"SELECT token FROM api_token WHERE tenant_id={sql_literal(tenant_id)} ORDER BY create_time DESC LIMIT 1;"
    )
    token = existing or f"luoying-ragflow-{secrets.token_urlsafe(32)}"
    now_ms, now_dt = current_times()
    mysql.execute(
        f"""
        INSERT INTO api_token
          (tenant_id, token, dialog_id, source, beta, create_time, create_date, update_time, update_date)
        VALUES
          ({sql_literal(tenant_id)}, {sql_literal(token)}, NULL, 'api', NULL,
           {now_ms}, {sql_literal(now_dt)}, {now_ms}, {sql_literal(now_dt)})
        ON DUPLICATE KEY UPDATE
          update_time=VALUES(update_time), update_date=VALUES(update_date), source=VALUES(source);
        """
    )
    return token


def ensure_dataset(
    mysql: RagflowMysql,
    *,
    ragflow_url: str,
    token: str,
    tenant_id: str,
    dataset_name: str,
    embedding_id: str,
) -> str:
    dataset_id = mysql.scalar(
        f"""
        SELECT id
        FROM knowledgebase
        WHERE tenant_id={sql_literal(tenant_id)} AND name={sql_literal(dataset_name)}
        ORDER BY create_time DESC
        LIMIT 1;
        """
    )
    if not dataset_id:
        payload = {
            "name": dataset_name,
            "embedding_model": embedding_id,
            "permission": "me",
            "parser_id": "naive",
        }
        response = request_json(
            method="POST",
            url=f"{ragflow_url}/api/v1/datasets",
            token=token,
            payload=payload,
        )
        data = response.get("data")
        dataset_id = str(data.get("id") if isinstance(data, dict) else "")
    if not dataset_id:
        raise RuntimeError("RAGFlow dataset was not created")

    now_ms, now_dt = current_times()
    mysql.execute(
        f"""
        UPDATE knowledgebase
        SET embd_id={sql_literal(embedding_id)}, update_time={now_ms}, update_date={sql_literal(now_dt)}
        WHERE id={sql_literal(dataset_id)};
        """
    )
    return dataset_id


def update_directus_site_dataset(
    *,
    directus_url: str,
    directus_token: str,
    site_id: str,
    dataset_id: str,
) -> bool:
    query = urllib.parse.urlencode(
        {
            "filter": json.dumps({"site_id": {"_eq": site_id}}, ensure_ascii=False),
            "limit": "1",
            "fields": "id,site_id,ragflow_dataset_id",
        }
    )
    url = f"{directus_url}/items/kb_sites?{query}"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {directus_token}"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print(f"Directus site update skipped: {exc}", file=sys.stderr)
        return False
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items:
        return False

    item_id = str(items[0]["id"])
    body = json.dumps({"ragflow_dataset_id": dataset_id}, ensure_ascii=False).encode("utf-8")
    patch = urllib.request.Request(
        f"{directus_url}/items/kb_sites/{urllib.parse.quote(item_id)}",
        data=body,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {directus_token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(patch, timeout=20):
        return True


def current_times() -> tuple[int, str]:
    now = datetime.now(timezone.utc)
    return int(time.time() * 1000), now.strftime("%Y-%m-%d %H:%M:%S")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap local RAGFlow models, API token, and dataset")
    parser.add_argument("--root-env", default=".env")
    parser.add_argument("--ragflow-env", default="deploy/kb/ragflow/.env")
    parser.add_argument("--mysql-container", default="luoying-ragflow-mysql-1")
    parser.add_argument("--ragflow-url", default=None)
    parser.add_argument("--dataset-name", default="sai_whu")
    parser.add_argument("--directus-site-id", default="sai_whu")
    parser.add_argument("--embedding-base-url", default="http://luoying-embedding:80")
    parser.add_argument("--embedding-model", default="BAAI/bge-small-zh-v1.5")
    parser.add_argument("--require-chat", action="store_true")
    args = parser.parse_args()

    root_env_path = Path(args.root_env)
    ragflow_env = parse_env(Path(args.ragflow_env))
    root_env = parse_env(root_env_path)
    mysql_password = ragflow_env.get("MYSQL_PASSWORD")
    mysql_database = ragflow_env.get("MYSQL_DBNAME", "rag_flow")
    if not mysql_password:
        raise RuntimeError(f"MYSQL_PASSWORD is missing in {args.ragflow_env}")

    ragflow_url = normalize_host_url(
        args.ragflow_url or root_env.get("RAGFLOW_URL") or "http://127.0.0.1:9380"
    )
    mysql = RagflowMysql(
        container=args.mysql_container,
        password=mysql_password,
        database=mysql_database,
    )
    tenant_id = mysql.scalar("SELECT id FROM tenant ORDER BY create_time LIMIT 1;")
    if not tenant_id:
        raise RuntimeError("No RAGFlow tenant found; wait until RAGFlow finishes initializing")

    api_token = ensure_api_token(
        mysql,
        tenant_id=tenant_id,
        preferred_token=root_env.get("RAGFLOW_API_KEY") or None,
    )
    embedding_id = register_embedding(
        mysql,
        tenant_id=tenant_id,
        base_url=args.embedding_base_url,
        model=args.embedding_model,
    )

    chat_id = ""
    chat_api_key = root_env.get("OPENAI_API_KEY", "")
    chat_base_url = root_env.get("OPENAI_BASE_URL", "")
    chat_model = root_env.get("OPENAI_MODEL", "")
    if chat_api_key and chat_base_url and chat_model:
        chat_id = register_chat(
            mysql,
            tenant_id=tenant_id,
            base_url=chat_base_url,
            api_key=chat_api_key,
            model=chat_model,
        )
    elif args.require_chat:
        raise RuntimeError("OPENAI_API_KEY, OPENAI_BASE_URL, and OPENAI_MODEL are required")

    dataset_id = ensure_dataset(
        mysql,
        ragflow_url=ragflow_url,
        token=api_token,
        tenant_id=tenant_id,
        dataset_name=args.dataset_name,
        embedding_id=embedding_id,
    )

    update_env(
        root_env_path,
        {
            "RAGFLOW_URL": "http://127.0.0.1:9380",
            "RAGFLOW_API_KEY": api_token,
            "RAGFLOW_SEARCH_PATH": "/api/v1/retrieval",
            "RAGFLOW_DEFAULT_DATASET_ID": dataset_id,
        },
    )

    directus_updated = False
    directus_url = root_env.get("DIRECTUS_URL", "")
    directus_token = root_env.get("DIRECTUS_TOKEN", "")
    if args.directus_site_id and directus_url and directus_token:
        directus_updated = update_directus_site_dataset(
            directus_url=normalize_host_url(directus_url),
            directus_token=directus_token,
            site_id=args.directus_site_id,
            dataset_id=dataset_id,
        )

    print(
        json.dumps(
            {
                "ok": True,
                "tenant_id": tenant_id,
                "embedding_model": embedding_id,
                "chat_model": chat_id or None,
                "dataset_name": args.dataset_name,
                "dataset_id": dataset_id,
                "directus_site_updated": directus_updated,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
