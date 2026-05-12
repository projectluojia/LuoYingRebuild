from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Dict, List, Optional

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

    async def upload_file(self, context: ChatContext, file: str):
        await self._emit(context, {"type": "file", "file": file})

    async def send_script_result(self, context: ChatContext, result: Dict[str, Any]) -> None:
        await self._emit(context, {"type": "script_result", "result": result})

    async def get_group_members(self, context: ChatContext) -> List[Dict[str, Any]]:
        raise TransportCapabilityError("Web transport 不支持获取群成员")

    async def fetch_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        raise TransportCapabilityError("Web transport 不支持获取消息详情")

    async def download_image(self, file_name: str) -> Optional[str]:
        return file_name
