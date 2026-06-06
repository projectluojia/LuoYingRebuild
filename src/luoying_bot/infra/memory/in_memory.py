from __future__ import annotations
from collections import defaultdict,deque
from datetime import datetime, timedelta, timezone
from luoying_bot.domain.context import ChatContext, UserIdentity
from luoying_bot.domain.message import UniMessage
from luoying_bot.domain.result import Reply
from luoying_bot.ports.memory import ConversationMemory, ConversationThread

class InMemoryConversationMemory(ConversationMemory):
    def __init__(self, max_messages_per_thread: int = 50):
        #用一个字典维护内存级记忆
        #key是线程id
        #列表是消息列表
        self._max_messages_per_thread = max(1, int(max_messages_per_thread))
        self._threads: dict[str, ConversationThread] = {}
        self._storage: dict[str, deque[tuple[str, UniMessage | Reply]]] = defaultdict(
            lambda: deque(maxlen=self._max_messages_per_thread)
        )
    def _now(self)-> datetime:
        return datetime.now(timezone(timedelta(hours=8)))
    
    def _title_from_hint(self,title_hint:str)->str:
        title = title_hint.strip().replace("\n"," ")
        if not title:
            return "新对话"
        if len(title)>30:
            return title[:30]+"..."
        return title

    def _touch(self,thread_id:str)->None:
        thread=self._threads.get(thread_id)
        if thread is not None:
            thread.updated_at=self._now()
    
    def _render_user_message(self, message: UniMessage) -> str:
        return message.to_llm_text().strip() or message.get_plain_text().strip()
    
    def _render_history_items(self, items: list[tuple[str, UniMessage | Reply]]) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for role, item in items:
            if role == "user" and isinstance(item, UniMessage):
                content = self._render_user_message(item)
            elif role == "assistant" and isinstance(item, Reply):
                content = item.text.strip()
            else:
                content = ""

            if content:
                messages.append({"role": role, "content": content})
        return messages
    
    def ensure_thread(self, context: ChatContext, title_hint: str = "") -> ConversationThread:
        thread_id = context.thread_id
        existing = self._threads.get(thread_id)
        if existing is not None:
            existing.updated_at = self._now()
            if existing.title == "新对话" and title_hint.strip():
                existing.title = self._title_from_hint(title_hint)
            return existing

        now = self._now()
        thread = ConversationThread(
            thread_id=thread_id,
            context=context,
            title=self._title_from_hint(title_hint),
            created_at=now,
            updated_at=now,
        )
        self._threads[thread_id] = thread
        return thread

    def get_thread(self, thread_id: str) -> ConversationThread | None:
        return self._threads.get(thread_id)
    
    def list_threads(
        self,
        user: UserIdentity | None = None,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
    ) -> list[ConversationThread]:
        items = list(self._threads.values())

        if user is not None:
            items = [
                item for item in items
                if item.context is not None
                and item.context.user.user_id == user.user_id
            ]

        if not include_archived:
            items = [item for item in items if not item.archived]

        items.sort(key=lambda item: item.updated_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return items[offset:offset + limit]

    def append_user(self, message: UniMessage) -> None:
        if message.context is None:
            return

        content = self._render_user_message(message)
        self.ensure_thread(message.context, title_hint=content)
        self._storage[message.context.thread_id].append(("user", message))
        self._touch(message.context.thread_id)

    def append_assistant(self, context: ChatContext, reply: Reply) -> None:
        self.ensure_thread(context)
        self._storage[context.thread_id].append(("assistant", reply))
        self._touch(context.thread_id)

    def read(self, thread_id: str, limit: int = 1000) -> list[dict[str, str]]:
        thread = self._threads.get(thread_id)
        items = self._storage.get(thread_id)

        messages: list[dict[str, str]] = []
        if thread is not None and thread.summary.strip():
            messages.append({
                "role": "system",
                "content": f"以下是此前对话的压缩摘要，供延续上下文使用：\n{thread.summary.strip()}",
            })

        if not items:
            return messages

        messages.extend(self._render_history_items(list(items)[-limit:]))
        return messages

    def read_for_summary(self, thread_id: str, keep_last: int) -> list[dict[str, str]]:
        thread = self._threads.get(thread_id)
        items = list(self._storage.get(thread_id) or [])
        if keep_last > 0:
            items = items[:-keep_last]
        messages: list[dict[str, str]] = []

        if thread is not None and thread.summary.strip():
            messages.append({
                "role": "system",
                "content": f"已有旧摘要：\n{thread.summary.strip()}",
            })

        messages.extend(self._render_history_items(items))
        return messages

    def replace_older_history_with_summary(
        self,
        thread_id: str,
        summary: str,
        keep_last: int,
    ) -> None:
        thread = self._threads.get(thread_id)
        if thread is None:
            return

        items = list(self._storage.get(thread_id) or [])
        keep_items = items[-keep_last:] if keep_last > 0 else []
        removed_count = len(items) - len(keep_items)

        self._storage[thread_id] = deque(keep_items, maxlen=self._max_messages_per_thread)
        thread.summary = summary.strip()
        thread.summarized_message_count += max(0, removed_count)
        thread.updated_at = self._now()

    def clear(self, context: ChatContext) -> None:
        now = self._now()
        thread_id = context.thread_id
        thread = self._threads.get(thread_id)

        if thread is None:
            thread = ConversationThread(thread_id=thread_id)
            self._threads[thread_id] = thread

        thread.context = context
        thread.title = "新对话"
        thread.summary = ""
        thread.summarized_message_count = 0
        thread.created_at = now
        thread.updated_at = now
        thread.archived = False
        thread.metadata.clear()
        self._storage[thread_id].clear()

    def archive_thread(self, thread_id: str, archived: bool = True) -> ConversationThread | None:
        thread = self._threads.get(thread_id)
        if thread is None:
            return None

        thread.archived = archived
        thread.updated_at = self._now()
        return thread

    def delete_thread(self, thread_id: str) -> bool:
        existed = thread_id in self._threads or thread_id in self._storage
        self._threads.pop(thread_id, None)
        self._storage.pop(thread_id, None)
        return existed
