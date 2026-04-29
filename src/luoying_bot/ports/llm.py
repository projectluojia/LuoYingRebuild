from __future__ import annotations
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Dict, List

#底层模型
class ChatModel(ABC):
    @abstractmethod
    async def chat(self, messages: List[Dict[str, str]], temperature: float | None = None) -> str: ...

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        yield await self.chat(messages, temperature=temperature)
