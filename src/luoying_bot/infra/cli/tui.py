from __future__ import annotations

import shutil
import sys
import textwrap


class CliTui:
    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    MAGENTA = "\033[35m"
    YELLOW = "\033[33m"
    RED = "\033[31m"

    def __init__(self) -> None:
        self.width = max(60, min(100, shutil.get_terminal_size((88, 20)).columns))

    def banner(self) -> None:
        line = "-" * self.width
        print(f"{self.CYAN}{line}{self.RESET}")
        print(f"{self.BOLD}Luoying CLI{self.RESET} {self.DIM}欢迎使用珞樱 / 输入 exit 退出{self.RESET}")
        print(f"{self.CYAN}{line}{self.RESET}")

    def prompt(self) -> str:
        return self._clean_input(input(f"{self.GREEN}You>{self.RESET} "))

    def track(self, text: str) -> None:
        self._block("track", text, self.YELLOW)

    def assistant(self, text: str) -> None:
        self._block("Luoying", text, self.MAGENTA)

    def assistant_stream_start(self) -> None:
        print(f"{self.MAGENTA}Luoying>{self.RESET} ", end="", flush=True)

    def assistant_stream_delta(self, text: str) -> None:
        print(self._safe_text(str(text)), end="", flush=True)

    def assistant_stream_end(self) -> None:
        print()

    def file(self, path: str) -> None:
        self._block("file", path, self.CYAN)

    def error(self, text: str) -> None:
        self._block("error", text, self.RED)

    def info(self, text: str) -> None:
        print(f"{self.DIM}{text}{self.RESET}")

    def _block(self, title: str, text: str, color: str) -> None:
        prefix = f"{color}{title}>{self.RESET} "
        text = self._safe_text(str(text))
        content_width = max(20, self.width - len(title) - 2)
        lines: list[str] = []
        for raw_line in text.splitlines() or [""]:
            wrapped = textwrap.wrap(raw_line, width=content_width) or [""]
            lines.extend(wrapped)

        if not lines:
            print(prefix)
            return

        print(prefix + lines[0])
        pad = " " * (len(title) + 2)
        for line in lines[1:]:
            print(pad + line)

    def _safe_text(self, text: str) -> str:
        encoding = sys.stdout.encoding or "utf-8"
        return text.encode(encoding, errors="replace").decode(encoding, errors="replace")

    def _clean_input(self, text: str) -> str:
        text = text.strip()
        text = text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")
        for prefix in ("\ufeff", "ï»¿", "ďť", "锘"):
            if text.startswith(prefix):
                text = text[len(prefix):]
        return text.strip()
