#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_EXTENSIONS = {
    ".py", ".cpp", ".c", ".h", ".hpp",
    ".java", ".js", ".ts", ".tsx", ".jsx",
    ".go", ".rs", ".cs", ".php", ".swift",
    ".kt", ".kts", ".scala", ".sh", ".lua",
    ".html", ".css", ".scss", ".sass", ".less",
    ".vue", ".xml", ".json", ".yaml", ".yml",
    ".toml", ".md",
}

DEFAULT_IGNORE_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "env",
    ".env",
    "dist",
    "build",
    "target",
    "out",
    "bin",
    "obj",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    ".next",
    ".nuxt",
    "coverage",
}

COMMENT_PREFIXES = {
    ".py": ["#"],
    ".sh": ["#"],
    ".yaml": ["#"],
    ".yml": ["#"],
    ".toml": ["#"],
    ".rb": ["#"],
    ".pl": ["#"],
    ".lua": ["--"],
    ".sql": ["--"],

    ".c": ["//"],
    ".cpp": ["//"],
    ".h": ["//"],
    ".hpp": ["//"],
    ".java": ["//"],
    ".js": ["//"],
    ".ts": ["//"],
    ".tsx": ["//"],
    ".jsx": ["//"],
    ".go": ["//"],
    ".rs": ["//"],
    ".cs": ["//"],
    ".php": ["//", "#"],
    ".swift": ["//"],
    ".kt": ["//"],
    ".kts": ["//"],
    ".scala": ["//"],

    ".html": ["<!--"],
    ".xml": ["<!--"],
    ".md": [],
    ".json": [],
    ".css": ["/*"],
    ".scss": ["//", "/*"],
    ".sass": ["//"],
    ".less": ["//", "/*"],
    ".vue": ["//", "<!--", "/*"],
}


@dataclass
class FileStats:
    total: int = 0
    blank: int = 0
    comment: int = 0
    code: int = 0


def is_ignored(path: Path, ignore_dirs: set[str]) -> bool:
    return any(part in ignore_dirs for part in path.parts)


def iter_files(root: Path, extensions: set[str], ignore_dirs: set[str]) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if is_ignored(path.relative_to(root), ignore_dirs):
            continue
        if path.suffix.lower() in extensions:
            yield path


def count_file(path: Path) -> FileStats:
    ext = path.suffix.lower()
    prefixes = COMMENT_PREFIXES.get(ext, ["#"])

    stats = FileStats()
    in_block_comment = False

    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return stats

    for raw_line in text.splitlines():
        stats.total += 1
        line = raw_line.strip()

        if not line:
            stats.blank += 1
            continue

        # 处理块注释状态
        if in_block_comment:
            stats.comment += 1
            if "*/" in line or "-->" in line:
                in_block_comment = False
            continue

        # 单行注释
        if any(line.startswith(prefix) for prefix in prefixes if prefix not in ("/*", "<!--")):
            stats.comment += 1
            continue

        # 块注释起始
        if line.startswith("/*"):
            stats.comment += 1
            if "*/" not in line:
                in_block_comment = True
            continue

        if line.startswith("<!--"):
            stats.comment += 1
            if "-->" not in line:
                in_block_comment = True
            continue

        stats.code += 1

    return stats


def merge_stats(a: FileStats, b: FileStats) -> FileStats:
    return FileStats(
        total=a.total + b.total,
        blank=a.blank + b.blank,
        comment=a.comment + b.comment,
        code=a.code + b.code,
    )


def format_table(rows: list[tuple[str, FileStats]]) -> str:
    name_w = max(len("文件/类型"), *(len(name) for name, _ in rows))
    total_w = len("总行数")
    blank_w = len("空行")
    comment_w = len("注释行")
    code_w = len("代码行")

    def line_sep() -> str:
        return (
            f"+-{'-' * name_w}-+-{'-' * total_w}-+-{'-' * blank_w}-+-"
            f"{'-' * comment_w}-+-{'-' * code_w}-+"
        )

    out = [line_sep()]
    out.append(
        f"| {'文件/类型'.ljust(name_w)} | {'总行数'.rjust(total_w)} | "
        f"{'空行'.rjust(blank_w)} | {'注释行'.rjust(comment_w)} | {'代码行'.rjust(code_w)} |"
    )
    out.append(line_sep())

    for name, stat in rows:
        out.append(
            f"| {name.ljust(name_w)} | {str(stat.total).rjust(total_w)} | "
            f"{str(stat.blank).rjust(blank_w)} | {str(stat.comment).rjust(comment_w)} | "
            f"{str(stat.code).rjust(code_w)} |"
        )

    out.append(line_sep())
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="统计目录下代码行数")
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="要统计的根目录，默认当前目录",
    )
    parser.add_argument(
        "--by-ext",
        action="store_true",
        help="按文件类型汇总",
    )
    parser.add_argument(
        "--by-file",
        action="store_true",
        help="列出每个文件的统计",
    )
    parser.add_argument(
        "--ext",
        nargs="*",
        default=None,
        help="只统计指定扩展名，例如: --ext .py .cpp .js",
    )
    parser.add_argument(
        "--ignore",
        nargs="*",
        default=None,
        help="额外忽略的目录名，例如: --ignore data logs",
    )

    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists() or not root.is_dir():
        print(f"目录不存在或不是文件夹: {root}")
        return

    extensions = set(e.lower() if e.startswith(".") else f".{e.lower()}" for e in (args.ext or DEFAULT_EXTENSIONS))
    ignore_dirs = set(DEFAULT_IGNORE_DIRS)
    if args.ignore:
        ignore_dirs.update(args.ignore)

    files = sorted(iter_files(root, extensions, ignore_dirs))

    if not files:
        print("没有找到符合条件的文件。")
        return

    total_stats = FileStats()

    if args.by_file:
        rows: list[tuple[str, FileStats]] = []
        for file in files:
            stat = count_file(file)
            total_stats = merge_stats(total_stats, stat)
            rows.append((str(file.relative_to(root)), stat))
        rows.append(("TOTAL", total_stats))
        print(format_table(rows))
        return

    if args.by_ext:
        ext_map: dict[str, FileStats] = {}
        for file in files:
            stat = count_file(file)
            total_stats = merge_stats(total_stats, stat)
            ext = file.suffix.lower() or "[no_ext]"
            ext_map[ext] = merge_stats(ext_map.get(ext, FileStats()), stat)

        rows = sorted(ext_map.items(), key=lambda x: x[0])
        rows.append(("TOTAL", total_stats))
        print(format_table(rows))
        return

    for file in files:
        total_stats = merge_stats(total_stats, count_file(file))

    rows = [("TOTAL", total_stats)]
    print(format_table(rows))
    print(f"\n已统计文件数: {len(files)}")
    print(f"统计目录: {root}")


if __name__ == "__main__":
    main()