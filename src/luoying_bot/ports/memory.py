from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass,field
from datetime import datetime

from typing import Any

from luoying_bot.domain.context import ChatContext, UserIdentity
from luoying_bot.domain.message import UniMessage
from luoying_bot.domain.result import Reply


@dataclass(slots=True)
class ConversationThread:
    thread_id:str
    context:ChatContext|None=None
    title:str="新对话"

    summary:str=""
    summarized_message_count:int=0


    created_at:datetime|None=None
    updated_at:datetime|None=None

    archived:bool=False
    metadata:dict[str,Any]=field(default_factory=dict)






class ConversationMemory(ABC):
    @abstractmethod
    def ensure_thread(self, context: ChatContext, title_hint: str = "") -> ConversationThread: ...
    @abstractmethod
    def get_thread(self, thread_id: str) -> ConversationThread | None: ...
    @abstractmethod
    def list_threads(
        self,
        user: UserIdentity | None = None,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
    ) -> list[ConversationThread]: ...

    @abstractmethod
    def append_user(self, message: UniMessage) -> None: ...
    @abstractmethod
    def append_assistant(self, context: ChatContext, reply: Reply) -> None: ...
    @abstractmethod
    def read(self, thread_id: str, limit: int = 1000) -> list[dict[str, str]]: ...
    @abstractmethod
    def read_for_summary(self, thread_id: str, keep_last: int) -> list[dict[str, str]]: ...
    @abstractmethod
    def replace_older_history_with_summary(
        self,
        thread_id: str,
        summary: str,
        keep_last: int,
    ) -> None: ...

    @abstractmethod
    def clear(self, context: ChatContext) -> None: ...

    @abstractmethod
    def archive_thread(self, thread_id: str, archived: bool = True) -> ConversationThread | None: ...
    @abstractmethod
    def delete_thread(self, thread_id: str) -> bool: ...