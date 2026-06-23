from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Dict, List, Optional

from luoying_bot.domain.context import ChatContext, Platform
from luoying_bot.domain.message import UniMessage
from luoying_bot.ports.transport import ChatTransport, TransportCapabilityError


class CliTransport(ChatTransport):
    def __init__(self) -> None:
        self.platform = Platform.CLI
        self.events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def connect(self) -> None:
        return

    async def close(self) -> None:
        return

    async def recv_message(self) -> UniMessage:
        raise TransportCapabilityError("CLI transport 不支持被动接收消息")

    def format_mention(self, context: ChatContext, user_id: str) -> str:
        return ""

    async def send_text(self, context: ChatContext, text: str, *, split: bool = False) -> None:
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
                    await self.events.put({"type": "text_start", "context": context})
                    started = True
                await self.events.put(
                    {
                        "type": "text_delta",
                        "text": chunk,
                        "context": context,
                    }
                )
        finally:
            if started:
                await self.events.put({"type": "text_end", "context": context})

    async def send_track(
        self,
        context: ChatContext,
        text: str,
        *,
        kind: str = "agent_action",
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        await self.events.put(
            {
                "type": "track",
                "kind": kind,
                "text": text,
                "metadata": metadata or {},
                "context": context,
            }
        )

    async def upload_file(self, context: ChatContext, file: str):
        await self.events.put(
            {
                "type": "file",
                "file": file,
                "context": context,
            }
        )

    async def send_script_result(self, context: ChatContext, result: Dict[str, Any]) -> None:
        await self.events.put(
            {
                "type": "script_result",
                "result": result,
                "context": context,
            }
        )

    async def get_group_members(self, context: ChatContext) -> List[Dict[str, Any]]:
        raise TransportCapabilityError("CLI transport 不支持获取群成员")

    async def fetch_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        raise TransportCapabilityError("CLI transport 不支持获取消息详情")

    async def download_image(self, file_name: str) -> Optional[str]:
        return file_name
