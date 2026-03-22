from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def _check_python_version() -> CheckResult:
    version = sys.version_info
    ok = version >= (3, 11)
    return CheckResult(
        name="python_version",
        ok=ok,
        detail=f"Python {version.major}.{version.minor}.{version.micro}",
    )


def _check_required_imports() -> list[CheckResult]:
    modules = [
        "fastapi",
        "uvicorn",
        "websockets",
        "httpx",
        "pydantic",
        "PIL",
        "dotenv",
        "langchain",
        "langchain_openai",
        "langgraph",
    ]
    results: list[CheckResult] = []
    for module_name in modules:
        try:
            importlib.import_module(module_name)
            results.append(CheckResult(module_name, True, "ok"))
        except Exception as exc:
            results.append(CheckResult(module_name, False, f"{type(exc).__name__}: {exc}"))
    return results


def _check_project_imports() -> list[CheckResult]:
    modules = [
        "luoying_bot.config",
        "luoying_bot.domain.message",
        "luoying_bot.application.event_handler",
        "luoying_bot.main_web",
        "luoying_bot.main_qq",
    ]
    results: list[CheckResult] = []
    for module_name in modules:
        try:
            importlib.import_module(module_name)
            results.append(CheckResult(module_name, True, "ok"))
        except Exception as exc:
            results.append(CheckResult(module_name, False, f"{type(exc).__name__}: {exc}"))
    return results


def _check_data_files() -> list[CheckResult]:
    from luoying_bot.config import settings

    paths = {
        "quick_reply_file": settings.quick_reply_file,
        "user_db_file": settings.user_db_file,
        "reminder_db_file": settings.reminder_db_file,
        "memo_dir": settings.memo_dir,
        "script_workspace_dir": settings.script_workspace_dir,
    }
    results: list[CheckResult] = []
    for name, path in paths.items():
        target = Path(path)
        exists = target.exists()
        results.append(CheckResult(name, exists, str(target)))
    return results


def _check_web_factory() -> CheckResult:
    try:
        from luoying_bot.main_web import create_app

        app = create_app()
        has_app = app is not None
        return CheckResult("web_factory", has_app, "create_app() ok" if has_app else "create_app() returned None")
    except Exception as exc:
        return CheckResult("web_factory", False, f"{type(exc).__name__}: {exc}")


def _print_results(title: str, results: list[CheckResult]) -> bool:
    print(f"\n[{title}]")
    all_ok = True
    for result in results:
        status = "OK" if result.ok else "FAIL"
        print(f"- {status:<4} {result.name}: {result.detail}")
        all_ok = all_ok and result.ok
    return all_ok


def main() -> int:
    print("Luoying startup self-check")
    print(f"cwd={Path.cwd()}")

    overall_ok = True
    overall_ok &= _print_results("runtime", [_check_python_version()])
    overall_ok &= _print_results("dependencies", _check_required_imports())
    overall_ok &= _print_results("project_imports", _check_project_imports())

    try:
        data_results = _check_data_files()
    except Exception as exc:
        data_results = [CheckResult("data_files", False, f"{type(exc).__name__}: {exc}")]
    overall_ok &= _print_results("data_paths", data_results)

    overall_ok &= _print_results("factories", [_check_web_factory()])

    print("\nSummary:")
    print("- PASS: basic startup checks passed" if overall_ok else "- FAIL: some startup checks failed")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
