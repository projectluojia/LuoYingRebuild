from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import json

from luoying_bot.application.agent.skill_base import SkillRequest
from luoying_bot.application.agent.skill_registry import SkillRegistry
from luoying_bot.domain.message import UniMessage
from luoying_bot.domain.context import Platform,ChannelType
from luoying_bot.domain.result import Reply
from luoying_bot.infra.logging_setup import context_log_extra
from luoying_bot.ports.llm import ChatModel
from luoying_bot.ports.memory import ConversationMemory
from luoying_bot.ports.transport import TransportCapabilityError
from luoying_bot.constants import REACT_INSTRUCTION
from luoying_bot.system_prompt_parts import build_system_prompt

logger = logging.getLogger(__name__)

CLI_STREAM_REACT_INSTRUCTION = """1. 判断是否需要调用技能
2. 只有当用户明确要求查看、写入、修改、删除或清空长期记忆时，才调用长期记忆技能。
3. 如果需要，可以多步调用多个技能
4. 每次只能做一件事：要么调用一个技能，要么确认可以开始最终回答
5. 不要把内部推理过程直接暴露给用户
6. 当已有信息足够回答时，立即确认可以开始最终回答，不要继续调用技能

你必须严格只输出 JSON，且只能是以下两种之一：

1. 调用技能
{"type":"act","skill":"技能名","payload":{...},"summary":"一句给用户看的中间状态，说明这一步准备做什么"}

2. 确认可以开始最终回答
{"type":"ok_to_answer"}

规则：
- 不要输出 JSON 之外的任何内容
- 如果要调用技能，skill 必须来自可用技能列表
- payload 必须是 JSON 对象
- summary 必须简短、自然、面向用户，只说明当前要执行的操作，不要包含内部推理或不确定的承诺
- 如果用户只是闲聊、寒暄、简单问答，直接输出 ok_to_answer
- 如果用户要求查询个人资料、提醒、天气、备忘录等，优先考虑技能
- 如果前面的观察结果已经足够回答，就直接输出 ok_to_answer
"""

@dataclass
class AgentStep:
    kind: str
    content: str
    skill_name: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


class AgentService:
    def __init__(
        self,
        model:ChatModel,
        memory:ConversationMemory,
        skills:SkillRegistry,
        max_steps:int=20,
        skill_timeout_sec: float = 30.0,
        total_timeout_sec: float = 90.0,
    ):
        self.model=model
        self.memory=memory
        self.skills=skills
        self.max_steps=max_steps
        self.skill_timeout_sec=skill_timeout_sec
        self.total_timeout_sec=total_timeout_sec

    def _build_system_prompt(self, client_type: str, user_id: str) -> str:
        prompt_settings = self.skills.services.user_prompt_settings_service.get(user_id)
        return build_system_prompt(
            client_type=client_type,
            basic_style=prompt_settings.basic_style,
            extra_trait_levels=prompt_settings.extra_trait_levels,
        )

    def _select_system_prompt(self,platform: Platform,channel_type: ChannelType,user_id: str)->str:
        if platform == Platform.QQ and channel_type == ChannelType.GROUP:
            return self._build_system_prompt("qq_group", user_id)
        elif platform == Platform.QQ and channel_type == ChannelType.PRIVATE:
            return self._build_system_prompt("qq_private", user_id)
        elif platform == Platform.WHATSAPP :
            pass
        elif platform == Platform.FEISHU:
            pass
        elif platform == Platform.DINGDING:
            pass
        elif platform == Platform.WEB:
            return self._build_system_prompt("web", user_id)
        elif platform == Platform.CLI:
            return self._build_system_prompt("cli", user_id)

        return self._build_system_prompt("web", user_id)

    def _runtime_context_message(self) -> dict[str, str]:
        now = datetime.now(timezone(timedelta(hours=8)))
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        return {
            "role": "system",
            "content": (
                "【运行时上下文】\n"
                f"当前时间：{now:%Y-%m-%d %H:%M:%S}（{weekdays[now.weekday()]}，UTC+08:00）\n"
                "当用户提到今天、明天、昨天、本周、当前时间、截止日期等相对时间时，必须以这里的当前时间为准。"
            ),
        }

    def _build_react_messages(
        self,
        thread_id:str,
        user_text:str,
        user_memory_text:str,
        scratchpad:list[AgentStep],
        step_index:int,
        system_prompt:str,
        *,
        stream_final: bool = False,
    )->list[dict[str,str]]:
        history=self.memory.read(thread_id=thread_id)
        skill_summary=self.skills.summary()
        scratchpad_text=self._render_scratchpad(scratchpad)
        final_action = (
            '- {"type":"ok_to_answer"}'
            if stream_final
            else '- {"type":"final","answer":"..."}'
        )
        
        user_prompt=(
            f"当前是第 {step_index} 步。\n\n"
            f"可用技能如下：\n{skill_summary}\n\n"
            f"用户消息：\n{user_text}\n\n"
            f"你当前已有的中间记录如下：\n{scratchpad_text}\n\n"
            "现在请决定下一步，只能输出一个 JSON：\n"
            '- {"type":"act","skill":"技能名","payload":{...},"summary":"给用户看的短句，说明这一步要做什么"}\n'
            f"{final_action}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            self._runtime_context_message(),
            {"role": "system", "content": CLI_STREAM_REACT_INSTRUCTION if stream_final else REACT_INSTRUCTION},
        ]

        if user_memory_text.strip():
            messages.append({
                "role": "system",
                "content": (
                    "以下是 Memobase 保存的该用户长期记忆。"
                    "它不是本轮用户消息。仅在相关时参考；如果与用户本轮明确表述冲突，以本轮明确表述为准。\n\n"
                    f"{user_memory_text}"
                ),
            })

        messages.extend(history)
        messages.append({"role": "user", "content": user_prompt})
        return messages
    
    def _render_scratchpad(self,scratchpad:list[AgentStep])->str:
        if not scratchpad:
            return "(暂无)"
        parts:list[str]=[]
        for i,step in enumerate(scratchpad,start=1):
            if step.kind=="action":
                parts.append(f"{i}. Action: {step.content}")
            else:
                parts.append(f"{i}. Observation: {step.content}")
        return "\n".join(parts)
    
    def _normalize_skill_result(self,skill_result:Any)->str:
        if skill_result is None:
            return "技能返回空结果"
        text=getattr(skill_result,"text",None)
        data=getattr(skill_result,"data",None)

        if text and data:
            return f"{text}\n结构化数据：{self._json_dumps(data)}"
        if text:
            return str(text)
        if data is not None:
            return self._json_dumps(data)

        return str(skill_result)
    
    async def _fallback_answer(
        self,
        thread_id:str,
        user_text:str,
        user_memory_text:str,
        scratchpad:list[AgentStep],
        system_prompt: str,
        deadline: float | None,
    )->str:
        prompt=(
            f"用户消息：\n{user_text}\n\n"
            f"你已有的中间记录：\n{self._render_scratchpad(scratchpad)}\n\n"
            "你之前没有成功给出最终回答。现在请直接自然地回复用户，不要提技能、工具、JSON、调用过程。"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            self._runtime_context_message(),
        ]

        if user_memory_text.strip():
            messages.append({
                "role": "system",
                "content": (
                    "以下是该用户长期记忆。"
                    "仅在相关时参考；如果与本轮用户明确表述冲突，以本轮为准。\n\n"
                    f"{user_memory_text}"
                ),
            })

        messages.extend(self.memory.read(thread_id=thread_id))
        messages.append({"role": "user", "content": prompt})

        raw = await self._chat_with_budget(messages, deadline=deadline)
        """
        raw= await self._chat_with_budget(
            [
                {"role":"system","content":system_prompt},
                *self.memory.read(thread_id=thread_id),
                {"role":"user","content":prompt},
            ],
            deadline=deadline,
        )"""
        return raw.strip()

    def _json_dumps(self,obj:Any)->str:
        try:
            return json.dumps(obj,ensure_ascii=False)
        except Exception:
            return str(obj)

    def _safe_parse_action(self,text:str)->dict[str,Any]:
        try:
            data=json.loads(text.strip())
            if not isinstance(data,dict):
                raise ValueError("not dict")
        except Exception:
            return {"type":"invalid","raw":text}

        if data.get("type")=="final":
            answer=data.get("answer")
            if isinstance(answer, str) and answer.strip():
                return {"type": "final", "answer": answer}
            return {"type": "invalid", "raw": text}

        if data.get("type") == "ok_to_answer":
            return {"type": "ok_to_answer"}
        
        if data.get("type") == "act":
            skill = data.get("skill")
            payload = data.get("payload", {})
            summary = data.get("summary", "")
            if isinstance(skill, str) and skill.strip() and isinstance(payload, dict):
                if not isinstance(summary, str):
                    summary = ""
                return {
                    "type": "act",
                    "skill": skill,
                    "payload": payload,
                    "summary": summary.strip(),
                }
            return {"type": "invalid", "raw": text}
        
        return {"type": "invalid", "raw": text}

    def _build_action_track_text(
        self,
        *,
        skill_name: str,
        payload: dict[str, Any],
        summary: str,
    ) -> str:
        summary = summary.strip()
        if summary:
            return summary
        return f"我先调用 {skill_name} 处理这一步。"

    async def _send_action_track(
        self,
        message: UniMessage,
        *,
        step_index: int,
        skill_name: str,
        payload: dict[str, Any],
        summary: str,
    ) -> None:
        context = message.context
        if context is None:
            return

        transport = getattr(getattr(self.skills, "services", None), "transport", None)
        if transport is None:
            return

        track_text = self._build_action_track_text(
            skill_name=skill_name,
            payload=payload,
            summary=summary,
        )
        if not track_text:
            return

        metadata = {
            "step_index": step_index,
            "skill": skill_name,
            "payload": payload,
        }

        try:
            await transport.send_track(
                context,
                track_text,
                kind="agent_action",
                metadata=metadata,
            )
        except TransportCapabilityError:
            return
        except Exception:
            logger.warning("发送 Agent 中间状态失败", exc_info=True, extra=context_log_extra(context))
    

    def _render_user_message_for_agent(self, message: UniMessage) -> str:
        ctx = message.context

        sender_id = ""
        sender_name = ""
        platform = ""
        channel_type = ""
        conversation_id = ""

        if ctx is not None:
            if getattr(ctx, "user", None) is not None:
                sender_id = str(getattr(ctx.user, "user_id", "") or "")
                sender_name = str(getattr(ctx.user, "user_name", "") or "")
            if getattr(ctx, "target", None) is not None:
                platform = str(getattr(getattr(ctx.target, "platform", None), "value", getattr(ctx.target, "platform", "")) or "")
                channel_type = str(getattr(getattr(ctx.target, "channel_type", None), "value", getattr(ctx.target, "channel_type", "")) or "")
                conversation_id = str(getattr(ctx.target, "conversation_id", "") or "")

        message_text = message.to_llm_text()

        return (
            f"发送者ID：{sender_id}\n"
            f"发送者昵称：{sender_name}\n"
            f"平台：{platform}\n"
            f"会话类型：{channel_type}\n"
            f"会话ID：{conversation_id}\n"
            f"消息内容：\n{message_text}"
        )

    def _remaining_timeout(self,deadline:float | None)->float | None:
        if deadline is None:
            return None
        remaining = deadline - time.monotonic()
        return max(0.01, remaining)
    
    async def _chat_with_budget(self, messages: list[dict[str, str]], deadline: float | None) -> str:
        timeout = self._remaining_timeout(deadline)
        if timeout is None:
            return await self.model.chat(messages)
        return await asyncio.wait_for(self.model.chat(messages), timeout=timeout)

    async def _maybe_name_thread(self, thread_id: str, user_text: str, answer: str) -> None:
        thread = self.memory.get_thread(thread_id)
        if thread is None or thread.metadata.get("title_generated"):
            return

        history = [item for item in self.memory.read(thread_id) if item.get("role") in {"user", "assistant"}]
        if len(history) != 2:
            return

        try:
            title = await asyncio.wait_for(self.model.chat([
                {
                    "role": "system",
                    "content": (
                        "请根据用户第一条消息和助手第一条回复，为这个对话起一个简短标题。"
                        "只输出标题本身，不要解释，不要加引号，不超过18个中文字符。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"用户：{user_text}\n助手：{answer}",
                },
            ]), timeout=8)
        except Exception:
            logger.exception("生成对话标题失败")
            return

        title = title.strip().strip('"').strip("'").strip("“”‘’").replace("\n", " ")
        title = title[:18].strip()
        if not title:
            return

        thread.title = title
        thread.metadata["title_generated"] = True
        thread.updated_at = datetime.now(timezone(timedelta(hours=8)))

    async def _chat_stream_with_budget(
        self,
        messages: list[dict[str, str]],
        deadline: float | None,
    ) -> AsyncIterator[str]:
        stream = self.model.chat_stream(messages)
        while True:
            try:
                if deadline is None:
                    chunk = await anext(stream)
                else:
                    chunk = await asyncio.wait_for(
                        anext(stream),
                        timeout=self._remaining_timeout(deadline),
                    )
            except StopAsyncIteration:
                break
            yield chunk

    def _build_direct_answer_messages(
        self,
        thread_id: str,
        user_text: str,
        user_memory_text: str,
        scratchpad: list[AgentStep],
        system_prompt: str,
    ) -> list[dict[str, str]]:
        prompt = (
            f"用户消息：\n{user_text}\n\n"
            f"你已有的中间记录：\n{self._render_scratchpad(scratchpad)}\n\n"
            "现在请直接自然地回复用户。不要输出 JSON，不要提技能、工具、JSON、调用过程。"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            self._runtime_context_message(),
        ]

        if user_memory_text.strip():
            messages.append({
                "role": "system",
                "content": (
                    "以下是该用户长期记忆。"
                    "仅在相关时参考；如果与本轮用户明确表述冲突，以本轮为准。\n\n"
                    f"{user_memory_text}"
                ),
            })

        messages.extend(self.memory.read(thread_id=thread_id))
        messages.append({"role": "user", "content": prompt})
        return messages
    
    async def _run_skill_with_budget(self, skill, request: SkillRequest, deadline: float | None):
        timeout = self.skill_timeout_sec if self.skill_timeout_sec > 0 else None
        remaining = self._remaining_timeout(deadline)
        if remaining is not None:
            timeout = min(timeout, remaining) if timeout is not None else remaining
        if timeout is None:
            return await skill.run(request)
        return await asyncio.wait_for(skill.run(request), timeout=timeout)

    async def reply(self,message:UniMessage)->str:
        context=message.context
        extra=context_log_extra(context)
        start_at=time.monotonic()
        deadline=start_at+self.total_timeout_sec if self.total_timeout_sec>0 else None


        thread_id=message.context.thread_id
        raw_user_text=message.to_llm_text()
        user_text=self._render_user_message_for_agent(message)
        self.memory.ensure_thread(message.context, title_hint=user_text)
        pltf=message.platform
        cntp=message.context.target.channel_type
        user_id=str(message.context.user.user_id)
        system_prompt=self._select_system_prompt(pltf,cntp,user_id)
        user_memory_text=await self.skills.services.user_memory_service.build_prompt_block(
            user_id,
            latest_user_text=raw_user_text,
        )



        logger.info("主 Agent 开始处理消息", extra=extra)
        scratchpad: list[AgentStep]=[]
        answer=None

        invalid_action_count = 0
        max_invalid_actions = 3

        for step_index in range(1,self.max_steps+1):
            if deadline is not None and time.monotonic() >= deadline:
                scratchpad.append(AgentStep(kind="observation", content="总执行预算已耗尽，请直接给出最终回答。"))
                logger.warning("主 Agent 总预算耗尽，转入 fallback", extra=extra)
                break

            llm_messages=self._build_react_messages(
                thread_id=thread_id,
                user_text=user_text,
                user_memory_text=user_memory_text,
                scratchpad=scratchpad,
                step_index=step_index,
                system_prompt=system_prompt,
            )
            try:
                raw= await self._chat_with_budget(llm_messages,deadline=deadline)
            except asyncio.TimeoutError:
                scratchpad.append(AgentStep(kind="observation", content="模型思考超时，请直接给出最终回答。"))
                logger.warning("主模型思考超时，转入 fallback", extra=extra)
                break

            action=self._safe_parse_action(raw)

            if action["type"]=="final":
                invalid_action_count = 0
                answer=action["answer"].strip()
                break

            if action["type"]!="act":
                invalid_action_count += 1
                logger.warning(
                    "主模型输出了无效动作，第 %s/%s 次：%s",
                    invalid_action_count,
                    max_invalid_actions,
                    raw.strip(),
                    extra=extra,
                )
                if invalid_action_count >= max_invalid_actions:
                    logger.warning("主模型连续输出无效动作达到上限，转入 fallback", extra=extra)
                    break
                continue
            
            invalid_action_count = 0
            skill_name=action.get("skill","")
            payload=action.get("payload",{})
            summary=action.get("summary","")
            skill=self.skills.get(skill_name)

            if not skill:
                logger.warning(f"主模型调用了不存在的 Skill：{skill_name}", extra=extra)
                scratchpad.append(
                    AgentStep(
                        kind="observation",
                        skill_name=skill_name,
                        payload=payload,
                        content=f"技能 {skill_name} 不存在。请从可用技能中重新选择，或直接回答。"
                    )
                )
                continue

            await self._send_action_track(
                message,
                step_index=step_index,
                skill_name=skill_name,
                payload=payload,
                summary=summary,
            )
            
            scratchpad.append(
                AgentStep(
                    kind="action",
                    skill_name=skill_name,
                    payload=payload,
                    content=f"调用技能 {skill_name}，参数：{self._json_dumps(payload)}"
                )
            )
            logger.info("调用技能 %s",skill_name,extra=extra)
            
            try:
                skill_result=await self._run_skill_with_budget(
                    skill,
                    SkillRequest(
                        message=message,
                        context=message.context,
                        payload=payload,
                    ),
                    deadline=deadline,
                )
                observation_text=self._normalize_skill_result(skill_result)
            except asyncio.TimeoutError:
                observation_text = f"技能 {skill_name} 执行超时"
                logger.warning("技能 %s 执行超时", skill_name, extra=extra)
            except Exception as e:
                observation_text=f"技能 {skill_name} 执行失败：{type(e).__name__}: {e}"
                logger.exception("技能 %s 执行失败", skill_name, extra=extra)
            
            scratchpad.append(
                AgentStep(
                    kind="observation",
                    skill_name=skill_name,
                    payload=payload,
                    content=observation_text,
                )
            )

        if not answer:
            try:
                answer = await self._fallback_answer(
                    thread_id=thread_id,
                    user_text=user_text,
                    user_memory_text=user_memory_text,
                    scratchpad=scratchpad,
                    system_prompt=system_prompt,
                    deadline=deadline,
                )
            except asyncio.TimeoutError:
                answer = "我这边刚刚处理超时了，能再发一次或者换个更具体的说法吗？"
        
        self.memory.append_user(message)
        self.memory.append_assistant(message.context, Reply(text=answer))
        await self.skills.services.user_memory_service.record_turn(
            user_id=user_id,
            user_text=raw_user_text,
            assistant_text=answer,
        )
        await self._maybe_name_thread(thread_id, user_text, answer)
        logger.info("主 Agent 完成处理，耗时 %.2fs", time.monotonic() - start_at, extra=extra)
        return answer

    async def reply_stream(self, message: UniMessage) -> AsyncIterator[str]:
        context = message.context
        extra = context_log_extra(context)
        start_at = time.monotonic()
        deadline = start_at + self.total_timeout_sec if self.total_timeout_sec > 0 else None

        thread_id = message.context.thread_id
        raw_user_text = message.to_llm_text()
        user_text = self._render_user_message_for_agent(message)
        self.memory.ensure_thread(message.context, title_hint=user_text)
        pltf = message.platform
        cntp = message.context.target.channel_type
        user_id = str(message.context.user.user_id)
        system_prompt = self._select_system_prompt(pltf, cntp, user_id)
        user_memory_text = await self.skills.services.user_memory_service.build_prompt_block(
            user_id,
            latest_user_text=raw_user_text,
        )

        logger.info("主 Agent 开始处理流式消息", extra=extra)
        scratchpad: list[AgentStep] = []
        answer: str | None = None
        invalid_action_count = 0
        max_invalid_actions = 3

        for step_index in range(1, self.max_steps + 1):
            if deadline is not None and time.monotonic() >= deadline:
                scratchpad.append(AgentStep(kind="observation", content="总执行预算已耗尽，请直接给出最终回答。"))
                logger.warning("主 Agent 总预算耗尽，转入流式 fallback", extra=extra)
                break

            llm_messages = self._build_react_messages(
                thread_id=thread_id,
                user_text=user_text,
                user_memory_text=user_memory_text,
                scratchpad=scratchpad,
                step_index=step_index,
                system_prompt=system_prompt,
                stream_final=True,
            )
            try:
                raw = await self._chat_with_budget(llm_messages, deadline=deadline)
            except asyncio.TimeoutError:
                scratchpad.append(AgentStep(kind="observation", content="模型思考超时，请直接给出最终回答。"))
                logger.warning("主模型思考超时，转入流式 fallback", extra=extra)
                break

            action = self._safe_parse_action(raw)

            if action["type"] == "ok_to_answer":
                invalid_action_count = 0
                answer_parts: list[str] = []
                messages = self._build_direct_answer_messages(
                    thread_id=thread_id,
                    user_text=user_text,
                    user_memory_text=user_memory_text,
                    scratchpad=scratchpad,
                    system_prompt=system_prompt,
                )
                try:
                    async for chunk in self._chat_stream_with_budget(messages, deadline=deadline):
                        answer_parts.append(chunk)
                        yield chunk
                except asyncio.TimeoutError:
                    logger.warning("最终回答流式生成超时", extra=extra)
                answer = "".join(answer_parts).strip()
                break

            if action["type"] == "final":
                invalid_action_count = 0
                answer = action["answer"].strip()
                yield answer
                break

            if action["type"] != "act":
                invalid_action_count += 1
                logger.warning(
                    "主模型输出了无效动作，第 %s/%s 次：%s",
                    invalid_action_count,
                    max_invalid_actions,
                    raw.strip(),
                    extra=extra,
                )
                if invalid_action_count >= max_invalid_actions:
                    logger.warning("主模型连续输出无效动作达到上限，转入流式 fallback", extra=extra)
                    break
                continue

            invalid_action_count = 0
            skill_name = action.get("skill", "")
            payload = action.get("payload", {})
            summary = action.get("summary", "")
            skill = self.skills.get(skill_name)

            if not skill:
                logger.warning(f"主模型调用了不存在的 Skill：{skill_name}", extra=extra)
                scratchpad.append(
                    AgentStep(
                        kind="observation",
                        skill_name=skill_name,
                        payload=payload,
                        content=f"技能 {skill_name} 不存在。请从可用技能中重新选择，或直接回答。"
                    )
                )
                continue

            await self._send_action_track(
                message,
                step_index=step_index,
                skill_name=skill_name,
                payload=payload,
                summary=summary,
            )

            scratchpad.append(
                AgentStep(
                    kind="action",
                    skill_name=skill_name,
                    payload=payload,
                    content=f"调用技能 {skill_name}，参数：{self._json_dumps(payload)}"
                )
            )
            logger.info("调用技能 %s", skill_name, extra=extra)

            try:
                skill_result = await self._run_skill_with_budget(
                    skill,
                    SkillRequest(
                        message=message,
                        context=message.context,
                        payload=payload,
                    ),
                    deadline=deadline,
                )
                observation_text = self._normalize_skill_result(skill_result)
            except asyncio.TimeoutError:
                observation_text = f"技能 {skill_name} 执行超时"
                logger.warning("技能 %s 执行超时", skill_name, extra=extra)
            except Exception as e:
                observation_text = f"技能 {skill_name} 执行失败：{type(e).__name__}: {e}"
                logger.exception("技能 %s 执行失败", skill_name, extra=extra)

            scratchpad.append(
                AgentStep(
                    kind="observation",
                    skill_name=skill_name,
                    payload=payload,
                    content=observation_text,
                )
            )

        if not answer:
            try:
                answer = await self._fallback_answer(
                    thread_id=thread_id,
                    user_text=user_text,
                    user_memory_text=user_memory_text,
                    scratchpad=scratchpad,
                    system_prompt=system_prompt,
                    deadline=deadline,
                )
            except asyncio.TimeoutError:
                answer = "我这边刚刚处理超时了，能再发一次或者换个更具体的说法吗？"
            yield answer

        self.memory.append_user(message)
        self.memory.append_assistant(message.context, Reply(text=answer))
        await self.skills.services.user_memory_service.record_turn(
            user_id=user_id,
            user_text=raw_user_text,
            assistant_text=answer,
        )
        await self._maybe_name_thread(thread_id, user_text, answer)
        logger.info("主 Agent 完成流式处理，耗时 %.2fs", time.monotonic() - start_at, extra=extra)
