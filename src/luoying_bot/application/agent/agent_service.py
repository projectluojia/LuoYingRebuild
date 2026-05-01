from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import json

from luoying_bot.application.agent.skill_base import SkillRequest
from luoying_bot.application.agent.skill_registry import SkillRegistry
from luoying_bot.domain.message import UniMessage
from luoying_bot.domain.context import Platform,ChannelType
from luoying_bot.infra.logging_setup import context_log_extra
from luoying_bot.ports.llm import ChatModel
from luoying_bot.ports.memory import ConversationMemory
from luoying_bot.ports.transport import TransportCapabilityError
from luoying_bot.constants import CLI_SYSTEM_PROMPT,QQ_GROUP_SYSTEM_PROMPT,REACT_INSTRUCTION,WEB_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

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

    def _select_system_prompt(self,platform: Platform,channel_type: ChannelType)->str:
        if platform == Platform.QQ and channel_type == ChannelType.GROUP:
            return QQ_GROUP_SYSTEM_PROMPT
        elif platform == Platform.QQ and channel_type == ChannelType.PRIVATE:
            pass
        elif platform == Platform.WHATSAPP :
            pass
        elif platform == Platform.FEISHU:
            pass
        elif platform == Platform.DINGDING:
            pass
        elif platform == Platform.WEB:
            return WEB_SYSTEM_PROMPT
        elif platform == Platform.CLI:
            return CLI_SYSTEM_PROMPT

        return WEB_SYSTEM_PROMPT

    def _build_react_messages(
        self,
        thread_id:str,
        user_text:str,
        user_memory_text:str,
        scratchpad:list[AgentStep],
        step_index:int,
        system_prompt:str,
    )->list[dict[str,str]]:
        history=self.memory.read(thread_id=thread_id)
        skill_summary=self.skills.summary()
        scratchpad_text=self._render_scratchpad(scratchpad)
        
        user_prompt=(
            f"当前是第 {step_index} 步。\n\n"
            f"可用技能如下：\n{skill_summary}\n\n"
            f"用户消息：\n{user_text}\n\n"
            f"你当前已有的中间记录如下：\n{scratchpad_text}\n\n"
            "现在请决定下一步，只能输出一个 JSON：\n"
            '- {"type":"act","skill":"技能名","payload":{...},"summary":"给用户看的短句，说明这一步要做什么"}\n'
            '- {"type":"final","answer":"..."}'
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": REACT_INSTRUCTION},
        ]

        if user_memory_text.strip():
            messages.append({
                "role": "system",
                "content": (
                    "以下是系统保存的该用户长期记忆。这是一段简短的用户简介。"
                    "它不是本轮用户消息。仅在相关时参考；如果与用户本轮明确表述冲突，以本轮明确表述为准。\n\n"
                    f"{user_memory_text}"
                ),
            })

        messages.extend(history)
        messages.append({"role": "user", "content": user_prompt})
        return messages

        """
        return [
            {"role":"system","content":system_prompt},
            {"role":"system","content":REACT_INSTRUCTION},
            *history,
            {"role":"user","content":user_prompt},
        ]"""
    
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
        ]

        if user_memory_text.strip():
            messages.append({
                "role": "system",
                "content": (
                    "以下是系统保存的该用户长期记忆。这是一段简短的用户简介。"
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
        user_text=self._render_user_message_for_agent(message)
        pltf=message.platform
        cntp=message.context.target.channel_type
        system_prompt=self._select_system_prompt(pltf,cntp)
        user_id=str(message.context.user.user_id)
        user_memory_text=self.skills.services.user_memory_service.build_prompt_block(user_id)



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
        
        self.memory.append(thread_id,"user",user_text)
        self.memory.append(thread_id,"assistant",answer)
        logger.info("主 Agent 完成处理，耗时 %.2fs", time.monotonic() - start_at, extra=extra)
        return answer
