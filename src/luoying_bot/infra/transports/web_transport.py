from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from luoying_bot.config import settings
from luoying_bot.domain.context import ChatContext, Platform
from luoying_bot.domain.message import UniMessage
from luoying_bot.ports.transport import ChatTransport, TransportCapabilityError


class WebTransport(ChatTransport):
    def __init__(self) -> None:
        self.platform = Platform.WEB
        self._request_queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}

    async def connect(self) -> None:
        return

    async def close(self) -> None:
        self._request_queues.clear()

    async def recv_message(self) -> UniMessage:
        raise TransportCapabilityError("Web transport 不支持被动接收消息")

    def register_request(self, request_uid: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._request_queues[request_uid] = queue
        return queue

    def unregister_request(self, request_uid: str) -> None:
        self._request_queues.pop(request_uid, None)

    async def _emit(self, context: ChatContext, event: dict[str, Any]) -> None:
        request_uid = str(context.request_uid or "")
        queue = self._request_queues.get(request_uid)
        if queue is not None:
            await queue.put({**event, "context": context})

    def format_mention(self, context: ChatContext, user_id: str) -> str:
        return ""

    async def send_text(self, context: ChatContext, text: str) -> None:
        async def chunks() -> AsyncIterator[str]:
            yield text

        await self.send_text_iter(context, chunks())

    async def send_text_iter(
        self,
        context: ChatContext,
        chunks: AsyncIterator[str],
    ) -> None:
        started = False
        try:
            async for chunk in chunks:
                if not chunk:
                    continue
                if not started:
                    await self._emit(context, {"type": "text_start"})
                    started = True
                await self._emit(context, {"type": "text_delta", "text": chunk})
        finally:
            if started:
                await self._emit(context, {"type": "text_end"})

    async def send_track(
        self,
        context: ChatContext,
        text: str,
        *,
        kind: str = "agent_action",
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        await self._emit(
            context,
            {
                "type": "track",
                "kind": kind,
                "text": text,
                "metadata": metadata or {},
            },
        )

    async def send_audio(
        self,
        context: ChatContext,
        audio_base64: str,
        volumes: list[float],
        emotion: str = "neutral",
        display_text: str = "",
        chunk_ms: int = 20,
        sample_rate: int = 24000,
        duration_ms: float = 0.0,
    ) -> None:
        """Send TTS audio + lip-sync volume data for frontend playback."""
        await self._emit(
            context,
            {
                "type": "audio",
                "audio": audio_base64,
                "volumes": volumes,
                "emotion": emotion,
                "text": display_text,
                "chunk_ms": chunk_ms,
                "sample_rate": sample_rate,
                "duration_ms": duration_ms,
            },
        )

    async def send_expression(
        self,
        context: ChatContext,
        emotion: str,
        text: str = "",
    ) -> None:
        """Send Live2D expression change (without audio)."""
        await self._emit(
            context,
            {
                "type": "expression",
                "emotion": emotion,
                "text": text,
            },
        )

    async def upload_file(self, context: ChatContext, file: str):
        target = Path(file).resolve()
        user_id = str(context.user.user_id)
        user_base = (settings.script_workspace_dir / user_id).resolve()
        event: dict[str, Any] = {
            "type": "file",
            "file": str(target),
            "file_name": target.name,
        }
        if user_base == target or user_base in target.parents:
            rel_path = target.relative_to(user_base).as_posix()
            event.update(
                {
                    "user_id": user_id,
                    "path": rel_path,
                    "size": target.stat().st_size if target.is_file() else 0,
                    "url": f"/download/{quote(user_id, safe='')}/{quote(rel_path, safe='/')}",
                }
            )
            await self._emit(
                context,
                {
                    "type": "track",
                    "kind": "file",
                    "text": f"文件已生成：{rel_path}",
                    "metadata": {
                        "file_name": target.name,
                        "path": rel_path,
                        "url": event["url"],
                        "size": event["size"],
                    },
                },
            )
        await self._emit(context, event)

    async def send_script_result(self, context: ChatContext, result: Dict[str, Any]) -> None:
        await self._emit(context, {"type": "script_result", "result": result})

    async def get_group_members(self, context: ChatContext) -> List[Dict[str, Any]]:
        raise TransportCapabilityError("Web transport 不支持获取群成员")

    async def fetch_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        raise TransportCapabilityError("Web transport 不支持获取消息详情")

    async def download_image(self, file_name: str) -> Optional[str]:
        if os.path.isabs(file_name) and os.path.isfile(file_name):
            return file_name

        raw = str(file_name or "").strip().replace("\\", "/")
        if not raw or raw.startswith("/"):
            return None
        parts = [part for part in raw.split("/") if part not in {"", "."}]
        if not parts or any(part == ".." for part in parts):
            return None

        base = settings.script_workspace_dir.resolve()
        target = (base / Path(*parts)).resolve()
        if (base == target or base in target.parents) and target.is_file():
            return str(target)

        return file_name
