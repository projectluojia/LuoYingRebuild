from __future__ import annotations

import json
import logging
import random
import re
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from luoying_bot.application.services.tts_service import GPTSoVITSTTSService, VolcanoTTSService

logger=logging.getLogger(__name__)

class EventHandler:
    def __init__(
            self, 
            transport: ChatTransport, 
            runtime: GroupRuntime, 
            commands: CommandDispatcher, 
            agent: AgentService, 
            quick_reply_service: QuickReplyService|None,
            risk_control_service: RiskControlService,
            trigger_prefix: list[str], 
            bot_qq: str, 
            bot_name: str,
            commands_enabled: bool = True,
            tts_service: VolcanoTTSService | GPTSoVITSTTSService | None = None,
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
        self.commands_enabled = commands_enabled
        self.tts_service = tts_service
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


        if self.quick_reply_service is not None and context.target.channel_type.value == 'group':
            quick_reply=self.quick_reply_service.match(text=query, context=context)
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
        if self.commands_enabled and query.startswith('/'):
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
        if context.target.platform in {Platform.CLI, Platform.WEB}:
            prefix = self.transport.format_mention(context, context.user.user_id)
            sent_parts: list[str] = []
            tts_buffer = ""

            async def output_chunks() -> AsyncIterator[str]:
                nonlocal tts_buffer
                if prefix:
                    sent_parts.append(prefix)
                    yield prefix
                try:
                    async for chunk in self.agent.reply_stream(message):
                        safe_chunk = self.risk_control_service.do_output_risk_control(str(chunk))
                        sent_parts.append(safe_chunk)
                        if context.target.platform == Platform.CLI:
                            yield safe_chunk
                            continue

                        tts_buffer += safe_chunk
                        ready, tts_buffer = self._pop_speakable_sentences(tts_buffer)
                        for sentence in ready:
                            await self._send_tts_sentence(context, sentence)
                            yield sentence
                except Exception:
                    if context.target.platform == Platform.CLI:
                        raise
                    logger.exception("Agent stream failed, using web voice fallback")
                    fallback = self._build_web_fallback_reply(message)
                    sent_parts.append(fallback)
                    tts_buffer += fallback

                if context.target.platform == Platform.WEB and tts_buffer.strip():
                    sentence = tts_buffer.strip()
                    await self._send_tts_sentence(context, sentence)
                    yield sentence
                    tts_buffer = ""

            logger.info("主 Agent 进入流式输出", extra=extra)
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

    def _pop_speakable_sentences(self, text: str) -> tuple[list[str], str]:
        clean = text.replace("\r", "\n")
        parts = re.split(r"([。！？!?；;\n])", clean)
        ready: list[str] = []
        current = ""
        for part in parts:
            if not part:
                continue
            current += part
            if re.fullmatch(r"[。！？!?；;\n]", part):
                sentence = current.strip()
                if sentence:
                    ready.append(sentence)
                current = ""

        if len(current) >= 28:
            comma_parts = re.split(r"([，,、])", current)
            current = ""
            for part in comma_parts:
                if not part:
                    continue
                current += part
                if re.fullmatch(r"[，,、]", part) and len(current) >= 16:
                    ready.append(current.strip())
                    current = ""
        return ready, current

    def _detect_tts_emotion(self, text: str) -> str:
        if any(token in text for token in ("开心", "高兴", "太好了", "欢迎", "喜欢", "恭喜")):
            return "happy"
        if any(token in text for token in ("抱歉", "难过", "遗憾", "辛苦")):
            return "sad"
        if any(token in text for token in ("注意", "严肃", "必须", "风险", "错误")):
            return "angry"
        if any(token in text for token in ("想一想", "分析", "推理", "也许", "可能")):
            return "thinking"
        return "gentle"

    def _build_web_fallback_reply(self, message: UniMessage) -> str:
        user_text = message.get_plain_text().strip() or message.to_llm_text().strip()
        if "欢迎" in user_text or "武汉大学" in user_text:
            return "欢迎来到武汉大学人工智能学院，我是珞樱。现在我正在用本地语音模式和你说话，等模型网络恢复后，就可以继续进行真实对话。"
        if "语音" in user_text or "同步" in user_text:
            return "我已经切到本地语音兜底模式了。文字会等语音片段准备好以后再显示，口型也会跟着音量变化一起动。"
        return "模型接口现在暂时连不上，不过珞樱的本地语音链路已经准备好了。我们可以先用这条链路测试字幕、语音和 Live2D 口型同步。"

    async def _send_tts_sentence(self, context, sentence: str) -> None:
        sentence = self._sanitize_tts_text(sentence)
        if not self.tts_service or not self._has_speakable_tts_content(sentence):
            return
        send_expression = getattr(self.transport, "send_expression", None)
        send_audio = getattr(self.transport, "send_audio", None)
        if send_audio is None:
            return

        emotion = self._detect_tts_emotion(sentence)
        if send_expression is not None:
            await send_expression(context, emotion=emotion, text=sentence)

        result = await self.tts_service.synthesize(sentence, emotion)
        if not result.audio_wav_base64:
            return
        await send_audio(
            context,
            result.audio_wav_base64,
            result.volumes,
            emotion=result.emotion,
            display_text=sentence,
            chunk_ms=result.chunk_ms,
            sample_rate=result.sample_rate,
            duration_ms=result.duration_ms,
        )

    def _sanitize_tts_text(self, text: str) -> str:
        clean = re.sub(r"[\U00010000-\U0010ffff]", "", text)
        clean = re.sub(r"`{1,3}.*?`{1,3}", "", clean)
        replacements = {
            "GPT-SoVITS": "本地语音模型",
            "GPT_SoVITS": "本地语音模型",
            "GPT": "大语言模型",
            "SoVITS": "语音模型",
            "Live2D": "动态角色",
            "live2d": "动态角色",
            "AI": "人工智能",
            "API": "接口",
            "LLM": "大模型",
            "HTTP": "网页请求",
            "SSE": "流式事件",
        }
        for raw, spoken in replacements.items():
            clean = clean.replace(raw, spoken)
        clean = re.sub(r"[A-Za-z][A-Za-z0-9_./:-]*", "", clean)
        clean = re.sub(r"\s+", " ", clean)
        return clean.strip()

    @staticmethod
    def _has_speakable_tts_content(text: str) -> bool:
        # GPT-SoVITS rejects punctuation-only chunks such as "!" or "？".
        return bool(re.search(r"[\w\u3400-\u9fff]", text, flags=re.UNICODE))
