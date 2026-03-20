from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List

#底层模型
class ChatModel(ABC):
    @abstractmethod
    async def chat(self, messages: List[Dict[str, str]], temperature: float | None = None) -> str: ...
