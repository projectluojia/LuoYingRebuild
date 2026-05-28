from __future__ import annotations
import random
from luoying_bot.config import settings
from luoying_bot.application.commands.base import BaseCommand
from luoying_bot.domain.context import ChatContext
from luoying_bot.domain.result import Reply

OFFICIAL_EMOJIS = [
    4, 5, 8, 9, 10, 12, 14, 16, 21, 23, 24, 25, 26, 27, 28, 29,
    30, 32, 33, 34, 38, 39, 41, 42, 43, 49, 53, 60, 63, 66, 74,
    75, 76, 78, 79, 85, 89, 96, 97, 98, 99, 100, 101, 102, 103,
    104, 106, 109, 111, 116, 118, 120, 122, 123, 124, 125, 129,
    144, 147, 171, 173, 174, 175, 176, 179, 180, 181, 182, 183,
    201, 203, 212, 214, 219, 222, 227, 232, 240, 243, 246, 262,
    264, 265, 266, 267, 268, 269, 270, 271, 272, 273, 277, 278,
    281, 282, 284, 285, 287, 289, 290, 293, 294, 297, 298, 299,
    305, 306, 307, 314, 315, 318, 319, 320, 322, 324, 326,
    9728, 9749, 9786, 10024, 10060, 10068, 127801, 127817,
    127822, 127827, 127836, 127838, 127847, 127866, 127867,
    127881, 128027, 128046, 128051, 128053, 128074, 128076,
    128077, 128079, 128089, 128102, 128104, 128147, 128157,
    128164, 128166, 128168, 128170, 128235, 128293, 128513,
    128514, 128516, 128522, 128524, 128527, 128530, 128531,
    128532, 128536, 128538, 128540, 128541, 128557, 128560,
    128563
]

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
class EmojiCommand(BaseCommand):
    name = '/emoji'
    args_required = True
    required_args = {'--code': ['-c']}
    async def validate(self, args):
        if not args['--code'].isdigit(): 
            raise ValueError('--id 必须是 TransportEmojiCode')

        return args
    async def execute(self, context, args):
        try:
            await self.services.transport.send_reaction(context, emoji_id=args['--code'])
        except Exception:
            pass

        if int(args['--code']) not in OFFICIAL_EMOJIS:
            return Reply(text='未知的表情代码，不保证可发出', silent=True)

        return Reply(text='', silent=True)

class EmojiRangeCommand(BaseCommand):
    name = '/emoji_range'
    args_required = True
    required_args = {'--left': ['-l'], '--right': ['-r']}
    async def validate(self, args): 
        if not args['--left'].isdigit() or not args['--right'].isdigit(): 
            raise ValueError('--left 和 --right 必须是数字')
        if int(args['--left']) > int(args['--right']): 
            raise ValueError('--left 必须小于或等于 --right')
        if int(args['--left']) - int(args['--right']) +1 > 10 :
            raise ValueError('一次查询范围不能超过 10')
        return args

    async def execute(self, context, args):
        success_send = {}
        for range_code in range(int(args['--left']), int(args['--right']) + 1):
            try:
                await self.services.transport.send_reaction(context, emoji_id=range_code)
                success_send[range_code] = True
            except Exception:
                pass

        return Reply(text=f"成功发送的表情代码：{', '.join(str(code) for code in success_send.keys())}", silent=True)




class EmojiListCommand(BaseCommand):
    name = '/emoji_list'
    async def validate(self, args): return args
    async def execute(self, context, args):
        return Reply(text=f"表情列表：https://bot.q.qq.com/wiki/develop/api-v2/openapi/emoji/model.html#EmojiType")


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