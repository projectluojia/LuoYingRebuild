from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass,field
from datetime import datetime
from typing import Optional
from luoying_bot.domain.context import ChatContext

#用户资料
@dataclass(slots=True)
class UserProfile:
    user_id: str
    department: str | None = None
    college: str | None = None
    year: str | None = None
    name: str | None = None


#提醒记录
@dataclass(slots=True)
class ReminderRecord:
    task_id: str
    user_id: str
    group_id: str
    run_time: datetime
    content: str
    context: ChatContext
    repeat: bool = False


#用户仓库基类
class UserRepo(ABC):
    @abstractmethod
    def get(self, user_id: str) -> Optional[UserProfile]: ...
    @abstractmethod
    def create(self, profile: UserProfile) -> None: ...
    @abstractmethod
    def update_fields(self, user_id: str, **fields: str | None) -> None: ...
    @abstractmethod
    def delete(self, user_id: str) -> bool: ...

#提醒基类
class ReminderRepo(ABC):
    @abstractmethod
    def list_by_user_and_group(self, user_id: str, group_id: str) -> list[ReminderRecord]: ...
    @abstractmethod
    def list_all(self) -> list[ReminderRecord]: ...
    @abstractmethod
    def save(self, record: ReminderRecord) -> None: ...
    @abstractmethod
    def delete_many(self, task_ids: list[str]) -> None: ...
    @abstractmethod
    def update_run_time(self, task_id: str, run_time: datetime) -> None: ...

@dataclass
class MemoItem:
    id: str
    content: str
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class MemoRepo(ABC):
    @abstractmethod
    def list_items(self, user_id: str) -> list[MemoItem]: ...

    @abstractmethod
    def save_items(self, user_id: str, items: list[MemoItem]) -> None: ...