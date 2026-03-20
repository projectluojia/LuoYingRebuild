from __future__ import annotations
from abc import ABC, abstractmethod

class ConversationMemory(ABC):
    @abstractmethod
    def append(self, thread_id: str, role: str, content: str) -> None: ...
    @abstractmethod
    def read(self, thread_id: str, limit: int = 1000) -> list[dict[str, str]]: ...
    @abstractmethod
    def clear(self, thread_id: str) -> None: ...
