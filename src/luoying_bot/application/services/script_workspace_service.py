from __future__ import annotations

import asyncio
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

from luoying_bot.domain.context import ChatContext
from luoying_bot.ports.transport import ChatTransport

@dataclass(slots=True)
class ScriptOpResult:
    ok: bool
    text: str
    data: dict

class ScriptWorkspaceService:
    def __init__(
        self,
        root_dir:Path,
        python_timeout_sec:int=15,
    ):
        self.root_dir=Path(root_dir)
        self.root_dir.mkdir(parents=True,exist_ok=True)
        self.python_timeout_sec=python_timeout_sec
    
    def _user_dir(self,user_id:str)->Path:
        path=self.root_dir/str(user_id)
        path.mkdir(parents=True,exist_ok=True)
        return path
    
    def _sanitive_relative_path(self, file_path:str)->str:
        raw=(file_path or "").strip().replace("\\",'/')
        if not raw:
            raise ValueError("file_path 不能为空")
        if raw.startswith("/"):
            raise ValueError("不允许绝对路径")
        parts = [p for p in raw.split("/") if p not in ("", ".")]
        if not parts:
            raise ValueError("非法文件路径")
        if any(part == ".." for part in parts):
            raise ValueError("不允许使用 ..")
        return "/".join(parts)
    
    def _resolve_user_file(self,user_id:str,file_path:str)->Path:
        rel=self._sanitive_relative_path(file_path)
        base=self._user_dir(user_id=user_id).resolve()
        target=(base/rel).resolve()
        if base != target and base not in target.parents:
            raise ValueError("文件路径越界")
        return target

    def _read_text_smart(self, target: Path) -> tuple[str, str]:
        raw = target.read_bytes()
        for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk", "big5"):
            try:
                return raw.decode(encoding), encoding
            except UnicodeDecodeError:
                continue
        return raw.decode("latin1"), "latin1"

    def list_scripts(self,user_id:str)->ScriptOpResult:
        base = self._user_dir(user_id=user_id)
        files = [p for p in base.rglob("*") if p.is_file()]
        rels = [
            str(p.relative_to(base)).replace("\\", "/")
            for p in files
        ]
        rels.sort()

        if not rels:
            return ScriptOpResult(True,"当前没有脚本文件",{"files":[]})
        lines = ["当前脚本文件："]
        lines.extend(f"{i}. {name}" for i, name in enumerate(rels, start=1))
        return ScriptOpResult(True,"\n".join(lines), {"files": rels})

    def read_script(self,user_id:str,file_path:str)->ScriptOpResult:
        target = self._resolve_user_file(user_id=user_id,file_path=file_path)
        if not target.exists() or not target.is_file():
            return ScriptOpResult(False, f"文件不存在：{file_path}", {"file_path": file_path})
        content, encoding = self._read_text_smart(target)
        return ScriptOpResult(
            True,
            f"文件内容如下（自动识别编码：{encoding}）：\n{content}",
            {"file_path": str(target), "content": content, "encoding": encoding},
        )

    def write_script(self, user_id: str, file_path: str, content: str, overwrite: bool = False) -> ScriptOpResult:
        target = self._resolve_user_file(user_id,file_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists() and not overwrite:
            return ScriptOpResult(
                False,
                f"文件已存在：{file_path}，如需覆盖请调用 overwrite",
                {"file_path": file_path},
            )
        
        target.write_text(content or "",encoding="utf-8")
        action = "已覆盖" if overwrite else "已创建"
        return ScriptOpResult(
            True,
            f"{action}脚本：{file_path}",
            {
                "file_path": str(target),
                "size": len(content or ""),
                "overwrite": overwrite,
            },
        )
    
    def delete_script(self, user_id: str, file_path: str) -> ScriptOpResult:
        target = self._resolve_user_file(user_id, file_path)
        if not target.exists() or not target.is_file():
            return ScriptOpResult(False, f"文件不存在：{file_path}", {"file_path": file_path})
        target.unlink()
        return ScriptOpResult(True, f"已删除脚本：{file_path}", {"file_path": file_path})

    async def run_python_script(self, user_id: str, file_path: str, args: str = "") -> ScriptOpResult:
        target = self._resolve_user_file(user_id, file_path)
        if not target.exists() or not target.is_file():
            return ScriptOpResult(False, f"文件不存在：{file_path}", {"file_path": file_path})

        if target.suffix.lower() != ".py":
            return ScriptOpResult(False, "只能运行 .py 文件", {"file_path": file_path})

        argv: List[str] = shlex.split(args or "")
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(target),
            *argv,
            cwd=str(target.parent),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.python_timeout_sec)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            out = ""
            err = f"脚本运行超时：{self.python_timeout_sec}s"
            combined = (
                f"script: {file_path}\n"
                f"args: {args or '(none)'}\n"
                f"exit_code: timeout\n\n"
                f"[stdout]\n(timeout before capture completed)\n\n"
                f"[stderr]\n{err}"
            )

            return ScriptOpResult(
                False,
                combined,
                {
                    "type": "script_result",
                    "file_path": file_path,
                    "args": args or "",
                    "returncode": None,
                    "timeout": self.python_timeout_sec,
                    "stdout": out,
                    "stderr": err,
                },
            )

        out = (stdout or b"").decode("utf-8", errors="replace")
        err = (stderr or b"").decode("utf-8", errors="replace")
        full_combined = (
            f"script: {file_path}\n"
            f"args: {args or '(none)'}\n"
            f"exit_code: {proc.returncode}\n\n"
            f"[stdout]\n{out or '(empty)'}\n\n"
            f"[stderr]\n{err or '(empty)'}"
        )
        return ScriptOpResult(
            proc.returncode == 0,
            full_combined,
            {
                "type": "script_result",
                "file_path": file_path,
                "args": args or "",
                "returncode": proc.returncode,
                "stdout": out,
                "stderr": err,
                "timeout": False,
            },
        )

    async def send_script_to_transport(
        self,
        user_id: str,
        file_path: str,
        context: ChatContext,
        transport: ChatTransport,
    ) -> ScriptOpResult:
        target = self._resolve_user_file(user_id, file_path)
        if not target.exists() or not target.is_file():
            return ScriptOpResult(False, f"文件不存在：{file_path}", {"file_path": file_path})

        await transport.upload_file(context=context, file=str(target))

        return ScriptOpResult(
            True,
            f"已发送脚本到当前会话：{file_path}",
            {"file_path": file_path},
        )
