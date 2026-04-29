from __future__ import annotations

import importlib
import inspect
import pkgutil

from luoying_bot.application.agent.skill_base import BaseSkill
from luoying_bot.application.service_hub import ServiceHub
from luoying_bot.domain.context import Platform


class SkillRegistry:
    def __init__(self, services: ServiceHub):
        self.services = services
        self.skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        self.skills[skill.name] = skill

    def auto_register(self, package: str = 'luoying_bot.application.agent.skills') -> None:
        module = importlib.import_module(package)
        for info in pkgutil.iter_modules(module.__path__):
            sub_module = importlib.import_module(f'{package}.{info.name}')
            for _, cls in inspect.getmembers(sub_module, inspect.isclass):
                if not issubclass(cls, BaseSkill) or cls is BaseSkill or cls.__module__ != sub_module.__name__:
                    continue
                if self.services.transport.platform in cls.platform:
                    self.register(cls(self.services))

    def summary(self) -> str:
        return '\n'.join(f'- {skill.name}: {skill.description}' for skill in self.skills.values())

    def get(self, name: str) -> BaseSkill | None:
        return self.skills.get(name)
