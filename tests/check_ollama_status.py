from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _load_env_file(root_dir: Path) -> None:
    env_path = root_dir / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_base_url(base_url: str) -> str:
    url = (base_url or "").strip().rstrip("/")
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"无效的 OLLAMA_BASE_URL: {base_url!r}")
    return url


def _derive_ollama_root(base_url: str) -> str:
    # 配置通常是 http://127.0.0.1:11434/v1，需要回退到 /api/* 根路径
    if base_url.endswith("/v1"):
        return base_url[:-3]
    return base_url


def _http_get_json(url: str, timeout: float) -> tuple[int, Any]:
    request = urllib.request.Request(url=url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = int(getattr(response, "status", 200))
        body = response.read().decode("utf-8", errors="replace")
    return status, json.loads(body) if body.strip() else {}


def _print_header(title: str) -> None:
    print(f"\n[{title}]")


def _print_ok(message: str) -> None:
    print(f"[OK] {message}")


def _print_warn(message: str) -> None:
    print(f"[WARN] {message}")


def _print_fail(message: str) -> None:
    print(f"[FAIL] {message}")


def _model_exists(config_model: str, online_models: list[str]) -> bool:
    if config_model in online_models:
        return True
    # 兼容 foo 与 foo:latest 这类差异
    if ":" not in config_model:
        return any(name.split(":", 1)[0] == config_model for name in online_models)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="检查 Ollama 服务状态（模型列表为空判定为错误）"
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="覆盖 OLLAMA_BASE_URL（例如 http://127.0.0.1:11434/v1）",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="HTTP 超时时间（秒），默认 5",
    )
    parser.add_argument(
        "--strict-model-match",
        action="store_true",
        help="严格模式：若配置的 OLLAMA_*_MODEL 不在在线模型列表中则判失败",
    )
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parents[1]
    _load_env_file(root_dir)

    raw_base_url = args.base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    use_local_ollama = _to_bool(os.getenv("USE_LOCAL_OLLAMA"), default=False)

    errors: list[str] = []
    warnings: list[str] = []

    _print_header("Basic")
    print(f"cwd={Path.cwd()}")
    print(f"root_dir={root_dir}")
    print(f"USE_LOCAL_OLLAMA={use_local_ollama}")
    print(f"OLLAMA_BASE_URL(raw)={raw_base_url}")

    try:
        base_url = _normalize_base_url(raw_base_url)
    except ValueError as exc:
        _print_fail(str(exc))
        return 1

    ollama_root = _derive_ollama_root(base_url)
    version_url = f"{ollama_root}/api/version"
    tags_url = f"{ollama_root}/api/tags"
    _print_ok(f"version_url={version_url}")
    _print_ok(f"tags_url={tags_url}")

    version_payload: Any = {}
    _print_header("Version")
    try:
        status, version_payload = _http_get_json(version_url, timeout=args.timeout)
        if status != 200:
            errors.append(f"/api/version 返回非 200：{status}")
        else:
            _print_ok("/api/version 可访问")
        version_text = (
            version_payload.get("version")
            if isinstance(version_payload, dict)
            else None
        )
        if version_text:
            _print_ok(f"Ollama version={version_text}")
        else:
            _print_warn("/api/version 响应中没有 version 字段")
    except urllib.error.HTTPError as exc:
        errors.append(f"/api/version HTTP 错误：{exc.code} {exc.reason}")
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, socket.timeout):
            errors.append("/api/version 超时，请检查服务状态或网络")
        else:
            errors.append(f"/api/version 连接失败：{reason}")
    except json.JSONDecodeError as exc:
        errors.append(f"/api/version 返回非 JSON：{exc}")
    except Exception as exc:
        errors.append(f"/api/version 未知错误：{type(exc).__name__}: {exc}")

    online_models: list[str] = []
    _print_header("Tags")
    try:
        status, tags_payload = _http_get_json(tags_url, timeout=args.timeout)
        if status != 200:
            errors.append(f"/api/tags 返回非 200：{status}")
        else:
            _print_ok("/api/tags 可访问")

        if not isinstance(tags_payload, dict):
            errors.append("/api/tags 返回体不是 JSON 对象")
        else:
            models = tags_payload.get("models")
            if not isinstance(models, list):
                errors.append("/api/tags 返回缺少 models 列表")
            elif len(models) == 0:
                # 用户要求：模型列表为空必须判失败
                errors.append("/api/tags 的 models 为空（判定为错误状态）")
            else:
                for model in models:
                    if not isinstance(model, dict):
                        continue
                    name = str(model.get("name") or model.get("model") or "").strip()
                    if name:
                        online_models.append(name)
                if not online_models:
                    errors.append("models 列表存在但没有可识别模型名（name/model）")
                else:
                    _print_ok(f"在线模型数量={len(online_models)}")
                    for name in online_models:
                        print(f"  - {name}")
    except urllib.error.HTTPError as exc:
        errors.append(f"/api/tags HTTP 错误：{exc.code} {exc.reason}")
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, socket.timeout):
            errors.append("/api/tags 超时，请检查服务状态或网络")
        else:
            errors.append(f"/api/tags 连接失败：{reason}")
    except json.JSONDecodeError as exc:
        errors.append(f"/api/tags 返回非 JSON：{exc}")
    except Exception as exc:
        errors.append(f"/api/tags 未知错误：{type(exc).__name__}: {exc}")

    _print_header("Model Checks")
    configured_models = [
        os.getenv("OLLAMA_MAIN_MODEL", "").strip(),
        os.getenv("OLLAMA_CODING_MODEL", "").strip(),
        os.getenv("OLLAMA_IMAGE_MODEL", "").strip(),
    ]
    configured_models = [m for m in configured_models if m]
    if not configured_models:
        warnings.append("未配置 OLLAMA_*_MODEL（将仅校验在线模型列表是否非空）")
    elif not online_models:
        warnings.append("未拿到在线模型列表，跳过配置模型匹配检查")
    else:
        missing: list[str] = []
        for cfg_model in configured_models:
            if _model_exists(cfg_model, online_models):
                _print_ok(f"配置模型可用：{cfg_model}")
            else:
                message = f"配置模型未在在线列表中找到：{cfg_model}"
                if args.strict_model_match:
                    missing.append(message)
                else:
                    warnings.append(message)
        errors.extend(missing)

    _print_header("Summary")
    for message in warnings:
        _print_warn(message)
    for message in errors:
        _print_fail(message)

    if errors:
        _print_fail("Ollama 状态检查失败")
        return 1

    _print_ok("Ollama 状态检查通过（在线模型列表非空）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
