from __future__ import annotations
from collections import defaultdict,deque
from luoying_bot.ports.memory import ConversationMemory

class InMemoryConversationMemory(ConversationMemory):
    def __init__(self, max_messages_per_thread: int = 50):
        #用一个字典维护内存级记忆
        #key是线程id
        #列表是消息列表
        self._max_messages_per_thread = max(1, int(max_messages_per_thread))
        self._storage: dict[str, deque[dict[str, str]]] = defaultdict(
            lambda: deque(maxlen=self._max_messages_per_thread)
        )
    
    def append(self, thread_id: str, role: str, content: str) -> None:
        #加一个消息
        self._storage[thread_id].append(
            {
                'role': role, 
                'content': content
            }
        )

    def read(self, thread_id: str, limit: int = 1000) -> list[dict[str, str]]:
        #读取
        items = self._storage.get(thread_id)
        if not items:
            return []
        return list(items)[-limit:]

    
    def clear(self, thread_id: str) -> None:
        #清掉
        self._storage.pop(thread_id, None)
