from __future__ import annotations

import json
import logging
import random
from collections.abc import AsyncIterator

from luoying_bot.application.agent.agent_service import AgentService
from luoying_bot.application.commands.dispatcher import CommandDispatcher
from luoying_bot.application.services.group_runtime import GroupRuntime
from luoying_bot.application.services.quick_reply_service import QuickReplyService
from luoying_bot.application.services.risk_control_service import RiskControlService
from luoying_bot.domain.message import UniMessage
from luoying_bot.domain.message import MessageSegment
from luoying_bot.domain.context import Platform
from luoying_bot.domain.result import Reply
from luoying_bot.infra.logging_setup import context_log_extra
from luoying_bot.ports.transport import ChatTransport
from luoying_bot.constants import NOTIFYS

logger=logging.getLogger(__name__)

class EventHandler:
    def __init__(
            self, 
            transport: ChatTransport, 
            runtime: GroupRuntime, 
            commands: CommandDispatcher, 
            agent: AgentService, 
            quick_reply_service: QuickReplyService,
            risk_control_service: RiskControlService,
            trigger_prefix: list[str], 
            bot_qq: str, 
            bot_name: str
        ):
        self.transport = transport
        self.runtime = runtime
        self.commands = commands
        self.agent = agent
        self.quick_reply_service=quick_reply_service
        self.risk_control_service=risk_control_service
        self.trigger_prefix = trigger_prefix
        self.bot_qq = str(bot_qq)
        self.bot_name = bot_name
    async def handle(self, message: UniMessage) -> Reply:
        context = message.context
        extra = context_log_extra(context)

        #沉默回复
        if not context: 
            return Reply(text='', silent=True)

        raw_event = message.raw_event or {}
        
    #    print(json.dumps(obj=raw_event,ensure_ascii=False,indent=4))

        logger.info("收到消息，开始处理",extra=extra)

        #如果用户被ban则沉默
        if self.runtime.is_user_banned(context.user.user_id): 
            logger.info("用户已被封禁，忽略消息",extra=extra)
            return Reply(text='', silent=True)

        #如果群聊不允许则沉默
        if context.target.platform.value == 'qq' and not self.runtime.is_group_enabled(context.target.conversation_id):
            logger.info("群未启用，忽略消息",extra=extra)
            return Reply(text='', silent=True)

        #特判戳一戳
        if raw_event.get('post_type') == 'notice' and raw_event.get('notice_type') == 'notify' and str(raw_event.get('target_id') or '') == self.bot_qq:
            #戳回去
            response=random.choice(NOTIFYS)
            await self.transport.group_poke(context, context.user.user_id)
            
            reply = Reply(text=response)
            await self.transport.send_text(context, reply.text)
            logger.info("命中戳一戳",extra=extra)
            return reply
        
        text = message.get_plain_text().strip() or message.to_llm_text().strip()
        query = self._normalize_query(text)
        mentioned = message.has_at(self.bot_qq)


        if context.target.channel_type.value == 'group':
            quick_reply=self.quick_reply_service.match(text=query)
            if quick_reply :
                await self.transport.send_text(context=message.context,text=quick_reply)
                logger.info("命中快速回复", extra=extra)
                return Reply(text='', silent=True)
        
        if not mentioned and context.target.platform.value =='qq':
            logger.info("收到 QQ 消息，但 mentioned 为 False",extra=extra)
            return Reply(text='', silent=True)
        """
        扩展指南：
        如果添加别的平台，此处可以添加类似代码：
        if not mentioned and context.target.platform.value =='dingding':
            return Reply(text='', silent=True)
        诸如此类。
        """



        #进入指令执行器
        if query.startswith('/'):
            logger.info("命中指令执行器",extra=extra)
            reply = await self.commands.dispatch(query, context) or Reply(text='未知命令')
            
            if not reply.silent and reply.text:
                prefix = self.transport.format_mention(context,context.user.user_id)    
                await self.transport.send_text(
                    context, 
                    prefix+reply.text,
                )
            return reply
        
        #如果处于复读模式
        if self.runtime.repeat_mode.get(context.target.conversation_id, False):
            logger.info("命中复读模式",extra=extra)
            query = self.risk_control_service.do_output_risk_control(query)
            reply = Reply(text=query)
            
            await self.transport.send_text(
                context, 
                reply.text
            )
            return reply
        
        #其他情况，进入agent处理

        message=self.risk_control_service.do_input_risk_control_any(message)
        if context.target.platform == Platform.CLI:
            prefix = self.transport.format_mention(context, context.user.user_id)
            sent_parts: list[str] = []

            async def output_chunks() -> AsyncIterator[str]:
                if prefix:
                    sent_parts.append(prefix)
                    yield prefix
                async for chunk in self.agent.reply_stream(message):
                    safe_chunk = self.risk_control_service.do_output_risk_control(str(chunk))
                    sent_parts.append(safe_chunk)
                    yield safe_chunk

            logger.info("主 Agent 进入 CLI 真流式输出", extra=extra)
            await self.transport.send_text_iter(context, output_chunks())
            return Reply(text=''.join(sent_parts))

        rp_msg=await self.agent.reply(message)
        rp_msg=self.risk_control_service.do_output_risk_control_any(rp_msg)
        reply = Reply(
            text=self.risk_control_service.do_output_risk_control(rp_msg)
        )
        
        
        if not reply.silent and reply.text:
            prefix = self.transport.format_mention(context,context.user.user_id) 
            logger.info("主 Agent 已返回 final",extra=extra)
            await self.transport.send_text(
                context, 
                prefix + reply.text
            )
        return reply
    
    def _normalize_query(self, text: str) -> str:
        return text.strip().replace(f'@{self.bot_name}', '').strip()
