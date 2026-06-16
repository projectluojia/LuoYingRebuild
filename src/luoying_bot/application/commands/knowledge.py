from __future__ import annotations

from luoying_bot.application.commands.base import BaseCommand
from luoying_bot.domain.context import ChatContext
from luoying_bot.domain.result import Reply


class KbAddCommand(BaseCommand):
    name = '/kb_add'
    aliases = ['/知识库添加']
    op_required = True
    args_required = True
    required_args = {
        '--title': ['-t'],
        '--content': ['-c'],
    }
    optional_args = {
        '--tags': ['-g'],
        '--source': ['-s'],
    }

    async def validate(self, args): return args

    async def execute(self, context: ChatContext, args: dict[str, str]):
        tags_raw = args.get('--tags', '')
        tags = [t.strip() for t in tags_raw.split(',') if t.strip()] if tags_raw else []
        result = self.services.knowledge_service.add_item(
            title=args['--title'],
            content=args['--content'],
            tags=tags,
            source=args.get('--source', ''),
        )
        return Reply(text=result.text)


class KbListCommand(BaseCommand):
    name = '/kb_list'
    aliases = ['/知识库列表']

    async def validate(self, args): return args

    async def execute(self, context: ChatContext, args: dict[str, str]):
        result = self.services.knowledge_service.list_items()
        return Reply(text=result.text)


class KbSearchCommand(BaseCommand):
    name = '/kb_search'
    aliases = ['/知识库搜索']
    args_required = True
    required_args = {
        '--keyword': ['-k'],
    }

    async def validate(self, args): return args

    async def execute(self, context: ChatContext, args: dict[str, str]):
        result = self.services.knowledge_service.search_items(keyword=args['--keyword'])
        return Reply(text=result.text)


class KbSummaryCommand(BaseCommand):
    name = '/kb_summary'
    aliases = ['/知识库摘要']

    async def validate(self, args): return args

    async def execute(self, context: ChatContext, args: dict[str, str]):
        result = await self.services.knowledge_service.generate_summary()
        return Reply(text=result.text)


class KbDelCommand(BaseCommand):
    name = '/kb_del'
    aliases = ['/知识库删除']
    op_required = True
    args_required = True
    required_args = {
        '--id': ['-i'],
    }

    async def validate(self, args): return args

    async def execute(self, context: ChatContext, args: dict[str, str]):
        result = self.services.knowledge_service.delete_item(item_id=args['--id'])
        return Reply(text=result.text)


class KbClearCommand(BaseCommand):
    name = '/kb_clear'
    aliases = ['/知识库清空']
    op_required = True

    async def validate(self, args): return args

    async def execute(self, context: ChatContext, args: dict[str, str]):
        result = self.services.knowledge_service.clear_all()
        return Reply(text=result.text)
