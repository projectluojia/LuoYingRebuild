#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _redact(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _join_api_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    if not base.endswith("/api/v1"):
        base = f"{base}/api/v1"
    return f"{base}/{path.lstrip('/')}"


def _request(
    method: str,
    url: str,
    *,
    token: str = "",
    body: dict[str, Any] | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "luoying-memobase-diagnose/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            parsed = _parse_json(text)
            return {
                "ok": 200 <= resp.status < 300,
                "status": resp.status,
                "elapsed_sec": round(time.monotonic() - started, 3),
                "headers": _interesting_headers(dict(resp.headers)),
                "json": parsed,
                "text": text[:4000],
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        text = raw.decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status": exc.code,
            "elapsed_sec": round(time.monotonic() - started, 3),
            "headers": _interesting_headers(dict(exc.headers)),
            "json": _parse_json(text),
            "text": text[:4000],
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": None,
            "elapsed_sec": round(time.monotonic() - started, 3),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=3),
        }


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text) if text else None
    except Exception:
        return None


def _interesting_headers(headers: dict[str, str]) -> dict[str, str]:
    keep = {
        "content-type",
        "content-length",
        "server",
        "date",
        "x-request-id",
    }
    return {k: v for k, v in headers.items() if k.lower() in keep}


def _embedding_test(embedding_url: str, timeout: float) -> dict[str, Any]:
    if not embedding_url:
        return {"skipped": True, "reason": "embedding_url is empty"}
    url = embedding_url.rstrip("/")
    if not url.endswith("/embeddings"):
        url = f"{url}/embeddings"
    result = _request(
        "POST",
        url,
        body={
            "input": "珞樱正在测试 Memobase 长期记忆 embedding",
            "model": "text-embeddings-inference",
            "encoding_format": "float",
        },
        timeout=timeout,
    )
    data = result.get("json")
    try:
        embedding = data["data"][0]["embedding"]
        result["embedding_dim"] = len(embedding)
        result["sample"] = embedding[:3]
        if "text" in result:
            result["text"] = "<omitted large embedding response>"
        if "json" in result:
            result["json"] = "<omitted large embedding response>"
    except Exception:
        result["embedding_dim"] = None
    return result


def _blob_body() -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat()
    return {
        "blob_type": "chat",
        "fields": {"source": "luoying_diag"},
        "blob_data": {
            "messages": [
                {
                    "role": "user",
                    "content": "我喜欢简洁直接的中文回答，也喜欢 Python 自动化。",
                    "created_at": created_at,
                },
                {
                    "role": "assistant",
                    "content": "记住了，我之后会尽量简洁，并优先给 Python 自动化方案。",
                    "created_at": created_at,
                },
            ]
        },
    }


def _test_user_flow(
    *,
    base_url: str,
    token: str,
    user_id: str,
    timeout: float,
) -> dict[str, Any]:
    encoded_user = urllib.parse.quote(user_id, safe="")
    steps: dict[str, Any] = {}
    steps["create_user"] = _request(
        "POST",
        _join_api_url(base_url, "/users"),
        token=token,
        body={"id": user_id, "data": {"source": "luoying_diag"}},
        timeout=timeout,
    )
    steps["get_user"] = _request(
        "GET",
        _join_api_url(base_url, f"/users/{encoded_user}"),
        token=token,
        timeout=timeout,
    )
    steps["insert_chat_blob"] = _request(
        "POST",
        _join_api_url(base_url, f"/blobs/insert/{encoded_user}?wait_process=false"),
        token=token,
        body=_blob_body(),
        timeout=timeout,
    )
    steps["flush_chat_buffer"] = _request(
        "POST",
        _join_api_url(base_url, f"/users/buffer/{encoded_user}/chat?wait_process=false"),
        token=token,
        timeout=timeout,
    )
    chats = urllib.parse.quote(
        json.dumps([{"role": "user", "content": "这个用户有什么偏好？"}], ensure_ascii=False),
        safe="",
    )
    steps["get_context"] = _request(
        "GET",
        _join_api_url(base_url, f"/users/context/{encoded_user}?max_token_size=800&chats_str={chats}"),
        token=token,
        timeout=timeout,
    )
    critical = ["create_user", "get_user", "insert_chat_blob", "flush_chat_buffer", "get_context"]
    steps["flow_ok"] = all(steps[name].get("ok") for name in critical)
    return steps


def _status_line(result: dict[str, Any]) -> str:
    if result.get("skipped"):
        return f"SKIP {result.get('reason')}"
    if result.get("status") is None:
        return f"ERR {result.get('error_type')}: {result.get('error')}"
    return f"{'OK' if result.get('ok') else 'FAIL'} HTTP {result.get('status')}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose LuoYing Memobase deployment.")
    parser.add_argument("--memobase-url", default=os.getenv("MEMOBASE_PROJECT_URL", "http://127.0.0.1:8019"))
    parser.add_argument("--memobase-key", default=os.getenv("MEMOBASE_API_KEY", "secret"))
    parser.add_argument("--embedding-url", default=os.getenv("MEMOBASE_DIAG_EMBEDDING_URL", "http://127.0.0.1:8080/v1"))
    parser.add_argument("--user-id", default=os.getenv("MEMOBASE_DIAG_USER_ID", "2564664062"))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("MEMOBASE_DIAG_TIMEOUT", "30")))
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    stamp = _now_stamp()
    raw_user_id = str(args.user_id)
    safe_user_id = "luoying_" + "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in raw_user_id)
    uuid_user_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"luoying:user:{raw_user_id}"))
    numeric_probe_id = f"999{int(time.time())}"
    diag_safe_id = f"{safe_user_id}_diag_{stamp.lower()}"
    diag_uuid_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"luoying:diag:{raw_user_id}:{stamp}"))

    report: dict[str, Any] = {
        "generated_at": stamp,
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
        },
        "config": {
            "memobase_url": args.memobase_url,
            "memobase_key": _redact(args.memobase_key),
            "embedding_url": args.embedding_url,
            "raw_user_id": raw_user_id,
            "safe_user_id": safe_user_id,
            "uuid_user_id": uuid_user_id,
            "timeout": args.timeout,
        },
        "tests": {},
        "recommendations": [],
    }

    tests = report["tests"]
    tests["memobase_healthcheck"] = _request(
        "GET",
        _join_api_url(args.memobase_url, "/healthcheck"),
        token=args.memobase_key,
        timeout=args.timeout,
    )
    tests["embedding"] = _embedding_test(args.embedding_url, args.timeout)

    raw_encoded = urllib.parse.quote(raw_user_id, safe="")
    tests["raw_user_get_readonly"] = _request(
        "GET",
        _join_api_url(args.memobase_url, f"/users/{raw_encoded}"),
        token=args.memobase_key,
        timeout=args.timeout,
    )

    test_ids = {
        "numeric_probe": numeric_probe_id,
        "safe_string_probe": diag_safe_id,
        "uuid_probe": diag_uuid_id,
    }
    tests["user_flows"] = {
        name: _test_user_flow(
            base_url=args.memobase_url,
            token=args.memobase_key,
            user_id=user_id,
            timeout=args.timeout,
        )
        for name, user_id in test_ids.items()
    }

    if not tests["memobase_healthcheck"].get("ok"):
        report["recommendations"].append("Memobase healthcheck failed. Check memobase container logs and MEMOBASE_PROJECT_URL/MEMOBASE_API_KEY.")
    if not tests["embedding"].get("ok"):
        report["recommendations"].append("Embedding endpoint failed. Check luoying-embedding logs and embedding_base_url.")
    elif tests["embedding"].get("embedding_dim") not in {512, 768, 1024, 1536, 2560}:
        report["recommendations"].append("Embedding endpoint responded, but dimension looks unexpected. Verify Memobase embedding_dim.")

    flows = tests["user_flows"]
    if flows["safe_string_probe"].get("flow_ok") and not flows["numeric_probe"].get("flow_ok"):
        report["recommendations"].append("Numeric-only Memobase user IDs appear problematic. Use a stable prefixed ID such as luoying_<app_user_id>.")
    if flows["uuid_probe"].get("flow_ok"):
        report["recommendations"].append(f"Stable UUID user IDs are accepted. Example for raw user {raw_user_id}: {uuid_user_id}.")
    if tests["raw_user_get_readonly"].get("status") == 422:
        report["recommendations"].append("GET for the raw application user ID returned HTTP 422. The bot should map application user IDs to Memobase-safe IDs.")
    if not report["recommendations"]:
        report["recommendations"].append("All core checks passed. If the bot still fails, compare its MEMOBASE_PROJECT_URL/MEMOBASE_API_KEY with this script.")

    output = Path(args.output) if args.output else Path(f"memobase_diagnosis_{stamp}.json")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Report written: {output}")
    print("Summary:")
    print(f"- memobase_healthcheck: {_status_line(tests['memobase_healthcheck'])}")
    print(f"- embedding: {_status_line(tests['embedding'])}, dim={tests['embedding'].get('embedding_dim')}")
    print(f"- raw_user_get_readonly: {_status_line(tests['raw_user_get_readonly'])}")
    for name, flow in tests["user_flows"].items():
        print(f"- {name}: {'OK' if flow.get('flow_ok') else 'FAIL'}")
        for step_name in ["create_user", "get_user", "insert_chat_blob", "flush_chat_buffer", "get_context"]:
            print(f"  - {step_name}: {_status_line(flow[step_name])}")
    print("Recommendations:")
    for item in report["recommendations"]:
        print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
