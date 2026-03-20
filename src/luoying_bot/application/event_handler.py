from __future__ import annotations

import random

from luoying_bot.application.agent.agent_service import AgentService
from luoying_bot.application.commands.dispatcher import CommandDispatcher
from luoying_bot.application.services.group_runtime import GroupRuntime
from luoying_bot.application.services.quick_reply_service import QuickReplyService
from luoying_bot.domain.message import UniMessage
from luoying_bot.domain.message import MessageSegment
from luoying_bot.domain.result import Reply
from luoying_bot.ports.transport import ChatTransport
from luoying_bot.constants import NOTIFYS

class EventHandler:
    def __init__(
            self, 
            transport: ChatTransport, 
            runtime: GroupRuntime, 
            commands: CommandDispatcher, 
            agent: AgentService, 
            quick_reply_service: QuickReplyService,
            trigger_prefix: list[str], 
            bot_qq: str, 
            bot_name: str
        ):
        self.transport = transport
        self.runtime = runtime
        self.commands = commands
        self.agent = agent
        self.quick_reply_service=quick_reply_service
        self.trigger_prefix = trigger_prefix
        self.bot_qq = bot_qq
        self.bot_name = bot_name
    async def handle(self, message: UniMessage) -> Reply:
        context = message.context

        #沉默回复
        if not context: 
            return Reply(text='', silent=True)

        raw_event = message.raw_event or {}
        
        #如果用户被ban则沉默
        if self.runtime.is_user_banned(context.user.user_id): 
            return Reply(text='', silent=True)
        
        #如果群聊不允许则沉默
        if context.target.platform.value == 'qq' and not self.runtime.is_group_enabled(context.target.conversation_id):
            return Reply(text='', silent=True)

        #特判戳一戳
        if raw_event.get('post_type') == 'notice' and raw_event.get('notice_type') == 'notify' and str(raw_event.get('target_id') or '') == self.bot_qq:
            #戳回去
            response=random.choice(NOTIFYS)
            await self.transport.group_poke(context, context.user.user_id)
            
            reply = Reply(text=response)
            await self.transport.send_text(context, reply.text)
            return reply
        
        text = message.get_plain_text().strip() or message.to_llm_text().strip()
        query = self._normalize_query(text)

        #快速回复
        quick_reply=self.quick_reply_service.match(text=query)
        if quick_reply :
            await self.transport.send_text(context=message.context,text=quick_reply)
            return Reply(text='', silent=True)
        
        if MessageSegment(type="at",data={"user_id":"3949843218"}) not in message.segments:
            return Reply(text='', silent=True)
        
        #进入指令执行器
        if query.startswith('/'):
            reply = await self.commands.dispatch(query, context) or Reply(text='未知命令')
            if not reply.silent and reply.text:
                await self.transport.send_text(
                    context, 
                    self._at_prefix(context) + reply.text if context.target.platform.value == 'qq' else reply.text
                )
            return reply
        
        #如果处于复读模式
        if self.runtime.repeat_mode.get(context.target.conversation_id, False):
            reply = Reply(text=query)
            await self.transport.send_text(
                context, 
                reply.text
            )
            return reply
        
        #其他情况，进入agent处理
        reply = Reply(text=await self.agent.reply(message))
        
        
        if not reply.silent and reply.text:
            await self.transport.send_text(context, self._at_prefix(context) + reply.text if context.target.platform.value == 'qq' else reply.text)
        return reply
    def _normalize_query(self, text: str) -> str:
        return text.strip().replace(f'@{self.bot_name}', '').strip()
    def _at_prefix(self, context) -> str:
        return f"[CQ:at,qq={context.user.user_id}] " if context.target.platform.value == 'qq' else ''
