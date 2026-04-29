from __future__ import annotations

import shutil
import sys
import textwrap


class CliTui:
    _RESET = "\033[0m"
    _DIM = "\033[2m"
    _BOLD = "\033[1m"
    _CYAN = "\033[36m"
    _GREEN = "\033[32m"
    _MAGENTA = "\033[35m"
    _YELLOW = "\033[33m"
    _RED = "\033[31m"

    def __init__(self) -> None:
        self.width = max(60, min(100, shutil.get_terminal_size((88, 20)).columns))
        self.use_color = sys.stdout.isatty()
        self._stream_indent = "  "
        self._stream_at_line_start = False

    def banner(self) -> None:
        title = " Luoying CLI "
        subtitle = " Agent shell / type exit to quit "
        line = "-" * self.width
        print()
        print(self._color(line, self._CYAN))
        print(
            self._color(title, self._BOLD)
            + self._color(subtitle, self._DIM)
        )
        print(self._color(line, self._CYAN))

    def prompt(self) -> str:
        prompt = self._color("\nYou", self._GREEN, self._BOLD) + self._color(" > ", self._DIM)
        return self._clean_input(input(prompt))

    def track(self, text: str) -> None:
        self._event("track", text, self._YELLOW)

    def assistant(self, text: str) -> None:
        self._block("Luoying", text, self._MAGENTA)

    def assistant_stream_start(self) -> None:
        self._section_header("Luoying", self._MAGENTA)
        print(self._stream_indent, end="", flush=True)
        self._stream_at_line_start = False

    def assistant_stream_delta(self, text: str) -> None:
        safe = self._safe_text(str(text))
        for char in safe:
            if self._stream_at_line_start and char != "\n":
                print(self._stream_indent, end="", flush=True)
                self._stream_at_line_start = False
            print(char, end="", flush=True)
            if char == "\n":
                self._stream_at_line_start = True

    def assistant_stream_end(self) -> None:
        print()

    def file(self, path: str) -> None:
        self._event("file", path, self._CYAN)

    def error(self, text: str) -> None:
        self._block("error", text, self._RED)

    def info(self, text: str) -> None:
        print(self._color(self._safe_text(str(text)), self._DIM))

    def _block(self, title: str, text: str, color: str) -> None:
        self._section_header(title, color)
        text = self._safe_text(str(text))
        content_width = max(20, self.width - 4)
        lines: list[str] = []
        for raw_line in text.splitlines() or [""]:
            wrapped = textwrap.wrap(raw_line, width=content_width) or [""]
            lines.extend(wrapped)

        if not lines:
            print()
            return

        for line in lines:
            print(f"  {line}")

    def _event(self, title: str, text: str, color: str) -> None:
        label = self._color(f"{title:<5}", color, self._BOLD)
        content = self._safe_text(str(text))
        content_width = max(20, self.width - 10)
        lines: list[str] = []
        for raw_line in content.splitlines() or [""]:
            wrapped = textwrap.wrap(raw_line, width=content_width) or [""]
            lines.extend(wrapped)

        if not lines:
            print(f"{label} |")
            return

        print(f"{label} | {lines[0]}")
        for line in lines[1:]:
            print(f"{'':5} | {line}")

    def _section_header(self, title: str, color: str) -> None:
        marker = self._color(title, color, self._BOLD)
        rule_len = max(8, self.width - len(title) - 3)
        rule = self._color("-" * rule_len, self._DIM)
        print(f"\n{marker} {rule}")

    def _safe_text(self, text: str) -> str:
        encoding = sys.stdout.encoding or "utf-8"
        return text.encode(encoding, errors="replace").decode(encoding, errors="replace")

    def _color(self, text: str, *codes: str) -> str:
        if not self.use_color or not codes:
            return text
        return "".join(codes) + text + self._RESET

    def _clean_input(self, text: str) -> str:
        text = text.strip()
        text = text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")
        for prefix in ("\ufeff", "ï»¿", "ďť", "锘"):
            if text.startswith(prefix):
                text = text[len(prefix):]
        return text.strip()
