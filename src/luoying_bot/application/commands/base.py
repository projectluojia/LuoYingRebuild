from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from luoying_bot.application.service_hub import ServiceHub
from luoying_bot.domain.context import ChatContext
from luoying_bot.domain.result import Reply

#指令基类
class BaseCommand(ABC):

    name: str = ''
    aliases: list[str] = [] #这个是指令别名
    op_required: bool = False
    args_required: bool = False
    required_args: dict[str, list[str]] = {}
    optional_args: dict[str, list[str]] = {}


    def __init__(self, services: ServiceHub):
        self.services = services

    #建立别名映射
    def _build_alias_map(self) -> dict[str, str]:
        alias_map: dict[str, str] = {}
        for canonical, aliases in {**self.required_args, **self.optional_args}.items():
            alias_map[canonical] = canonical
            for alias in aliases: 
                alias_map[alias] = canonical
        return alias_map
    
    #初步验证
    def _parse_args(self, args: list[str] | None) -> dict[str, str]:
        if not self.args_required:
            return {}
        if len(args) % 2 != 0: raise ValueError(f'参数数量应与值数量相等，但收到 {len(args)} 个内容块')
        alias_map = self._build_alias_map(); normalized: dict[str, str] = {}
        for raw_key, value in zip(args[::2], args[1::2]):
            if raw_key not in alias_map: raise ValueError(f'未知参数: {raw_key}')
            canonical = alias_map[raw_key]
            if canonical in normalized: raise ValueError(f'参数重复：{canonical}')
            normalized[canonical] = value
        missing = [key for key in self.required_args if key not in normalized]
        if missing: raise ValueError(f'缺少必需参数: {", ".join(missing)}')
        return normalized
    
    @abstractmethod
    async def validate(self, args: dict[str, str]) -> dict[str, str]: ...

    @abstractmethod
    async def execute(self, context: ChatContext, args: dict[str, str]) -> Reply: ...

    async def process(self, context: ChatContext, args: Optional[list[str]]) -> Reply:
        if self.op_required and context.user.user_id not in self.services.ops:
            return Reply(text='权限不足')
        parsed = await self.validate(self._parse_args(args))
        return await self.execute(context, parsed)
