from __future__ import annotations
from luoying_bot.application.commands.base import BaseCommand
from luoying_bot.domain.result import Reply

class YourCommand(BaseCommand):
    name = "/six_seven"
    async def validate(self, args): return args
    async def execute(self, context, args):
        return Reply(
            text="""刘夫妻🫳🫴小子🧒正在和刘琦先生🧑🏫闹矛盾💥🗣️刘夫妻小子最近在波波播课📱说了这个你和其他的六十七孩子有矛盾吗🤬是的✅你有吗你认为谁是六七真的的代表🤵MR六七还是六十七KID🤔🤔🤔"""
        )