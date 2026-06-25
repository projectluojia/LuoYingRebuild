from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict

from luoying_bot.application.service_hub import ServiceHub
from luoying_bot.domain.context import ChatContext
from luoying_bot.domain.message import UniMessage

@dataclass(slots=True)
class SkillRequest:
    message: UniMessage
    context: ChatContext
    payload: Dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class SkillResult:
    text: str
    data: dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    llm_observation: str | None = None
    final_append_text: str = ""

class BaseSkill(ABC):
    name: str = ''
    description: str = ''
    platform = []

    def __init__(self, services: ServiceHub): self.services = services

    @abstractmethod
    async def run(self, req: SkillRequest) -> SkillResult: ...
