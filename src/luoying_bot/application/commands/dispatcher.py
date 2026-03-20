from __future__ import annotations
import importlib, inspect, pkgutil
from luoying_bot.application.commands.base import BaseCommand
from luoying_bot.domain.context import ChatContext
from luoying_bot.domain.result import Reply

class CommandDispatcher:
    def __init__(self, services: dict):
        self.services = services
        self.commands: dict[str, BaseCommand] = {}

    #注册指令
    def register(self, command: BaseCommand) -> None:
        if command.name in self.commands: 
            raise ValueError(f'命令名重复: {command.name}')
        self.commands[command.name] = command
        for alias in command.aliases:
            if alias in self.commands: 
                raise ValueError(f'命令别名重复: {alias}')
            self.commands[alias] = command

    #自动注册器
    def auto_register(self, package: str = 'luoying_bot.application.commands') -> None:
        module = importlib.import_module(package)
        for info in pkgutil.iter_modules(module.__path__):
            if info.name in {'base', 'dispatcher'}: 
                continue
            sub_module = importlib.import_module(f'{package}.{info.name}')

            for _, cls in inspect.getmembers(sub_module, inspect.isclass):
                if not issubclass(cls, BaseCommand) or cls is BaseCommand or cls.__module__ != sub_module.__name__: 
                    continue
                self.register(cls(self.services))

    #分发
    async def dispatch(self, text: str, context: ChatContext) -> Reply | None:
        try:
            parts = text.split();
            if not parts: return None
            command = self.commands.get(parts[0])
            return None if not command else await command.process(context, parts[1:])
        except Exception as e:
            return Reply(text=f"出错：{e}")