from __future__ import annotations
import random
from luoying_bot.config import settings
from luoying_bot.application.commands.base import BaseCommand
from luoying_bot.domain.context import ChatContext
from luoying_bot.domain.result import Reply

#测试通过
class HelpCommand(BaseCommand):
    name = '/help'
    async def validate(self, args): return args

    async def execute(self, context, args):
        return Reply(text=f"请访问博客园链接获取帮助：{self.services.HELP}\n也可以在这个链接查看开发日志：{self.services.LOG}")

#测试通过
class ClearCommand(BaseCommand):
    name = '/clear'
    async def validate(self, args): return args
    async def execute(self, context, args):
        self.services.memory.clear(context.thread_id); 
        return Reply(text='已清除当前会话记忆')
"""
#测试通过
class RepeatCommand(BaseCommand):
    name = '/repeat'
    async def validate(self, args): return args
    async def execute(self, context, args):
        enabled = self.services.runtime.toggle_repeat(context.target.conversation_id)
        return Reply(text='复读模式已开启' if enabled else '复读模式已关闭')
"""
#测试通过
class BindCommand(BaseCommand):
    name = '/bind' 
    args_required = True
    required_args = {
        '--college': ['-c'], 
        '--year': ['-y'], 
        '--department': ['-d']
    } 
    optional_args = {
        '--name': ['-n']
    }
    async def validate(self, args):
        if not args['--year'].isdigit(): 
            raise ValueError('--year 必须是正整数')
        return args
    async def execute(self, context, args):
        return Reply(
            text=self.services.user_service.bind(
                context.user.user_id, 
                args['--department'], 
                args['--college'], 
                args['--year'], 
                args.get('--name')
            )
        )

#测试通过
class UpdCommand(BaseCommand):
    name = '/upd'
    args_required = True
    optional_args = {
        '--college': ['-c'], 
        '--year': ['-y'], 
        '--department': ['-d'], 
        '--name': ['-n']
    }
    async def validate(self, args):
        if ('--department' in args) ^ ('--college' in args): 
            raise ValueError('--department 和 --college 参数必须成对出现')
        if '--year' in args and not args['--year'].isdigit(): 
            raise ValueError('--year 必须是数字')
        return args
    async def execute(self, context, args):
        return Reply(
            text=self.services.user_service.update(
                context.user.user_id, 
                department=args.get('--department'), 
                college=args.get('--college'), 
                year=args.get('--year'), 
                name=args.get('--name')
            )
        )

#测试通过
class WithdrawCommand(BaseCommand):
    name = '/withdraw'
    async def validate(self, args): return args
    async def execute(self, context, args): 
        return Reply(text=self.services.user_service.delete(context.user.user_id))


class BanCommand(BaseCommand):
    name = '/ban'
    op_required = True
    args_required = True 
    required_args = {'--id': ['-i']}
    async def validate(self, args):
        if not args['--id'].isdigit(): 
            raise ValueError('--id 必须是 ChatTransport ID')
        return args
    async def execute(self, context, args):
        if args['--id'] in self.services.ops: 
            raise ValueError('操作对管理员无效')
        self.services.runtime.ban_user(args['--id']) 
        return Reply(text=f"已在全局阻塞来自 {args['--id']} 的消息")

class UnBanCommand(BaseCommand):
    name = '/unban'
    op_required = True
    args_required = True
    required_args = {'--id': ['-i']}
    async def validate(self, args):
        if not args['--id'].isdigit(): 
            raise ValueError('--id 必须是 ChatTransport ID')
        return args
    async def execute(self, context, args):
        if args['--id'] in self.services.ops: 
            raise ValueError('操作对管理员无效')
        self.services.runtime.unban_user(args['--id'])
        return Reply(text=f"已在全局放行来自 {args['--id']} 的消息")

#测试通过
class RefreshListCommand(BaseCommand):
    name = '/refresh_list'
    async def validate(self, args): return args
    async def execute(self, context, args):
        self.services.runtime.member_cache[context.target.conversation_id] = await self.services.transport.get_group_members(context)
        
        return Reply(text='已刷新群聊信息')

#测试通过
class RandomOneCommand(BaseCommand):
    name = '/random_one'
    async def validate(self, args): return args
    async def execute(self, context, args):
        members = await self.services.transport.get_group_members(context)
        self.services.runtime.member_cache[context.target.conversation_id] = members
        member = random.choice(members)
        return Reply(text=f"幸运儿是 {member.get('nickname', '匿名')}({member.get('user_id')}) 🎉")

#测试通过
class TitleCommand(BaseCommand):
    name = '/title'
    args_required = True
    required_args = {'--title': ['-t']}
    async def validate(self, args): return args
    async def execute(self, context, args):
        await self.services.transport.set_special_title(context, args['--title'])
        return Reply(silent=True,text='已设置头衔')

#测试通过
class RmTitleCommand(BaseCommand):
    name = '/rmtitle'
    async def validate(self, args): return args
    async def execute(self, context, args):
        await self.services.transport.set_special_title(context, '')
        return Reply(silent=True,text='已清除头衔')

#测试通过
class WholeBanCommand(BaseCommand):
    name = '/whole_ban' 
    op_required = True
    async def validate(self, args): return args
    async def execute(self, context, args):
        await self.services.transport.set_group_whole_ban(context, True)
        return Reply(text='已开启全员禁言')

#测试通过
class DisWholeBanCommand(BaseCommand):
    name = '/dis_whole_ban'
    op_required = True
    async def validate(self, args): return args
    async def execute(self, context, args):
        await self.services.transport.set_group_whole_ban(context, False)
        return Reply(text='已关闭全员禁言')

#测试通过
class AttachCommand(BaseCommand):
    name = '/attach'
    async def validate(self, args): return args
    async def execute(self, context, args):
        await self.services.transport.send_reaction(context, emoji_id=297)
        return Reply(text='', silent=True)

#测试通过
class DiceCommand(BaseCommand):
    name = '/dice'
    async def validate(self, args): return args
    async def execute(self, context, args):
        await self.services.transport.send_text(context, '[CQ:dice]')
        return Reply(text='', silent=True)

class VersionCommand(BaseCommand):
    name = '/version'
    async def validate(self, args): return args
    async def execute(self, context, args):
        await self.services.transport.send_text(context, f'目前运行的版本：{settings.version}')
        return Reply(text='', silent=True)