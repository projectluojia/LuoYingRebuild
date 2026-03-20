from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import json

from luoying_bot.application.agent.skill_base import SkillRequest
from luoying_bot.application.agent.skill_registry import SkillRegistry
from luoying_bot.domain.message import UniMessage
from luoying_bot.ports.llm import ChatModel
from luoying_bot.ports.memory import ConversationMemory
from luoying_bot.constants import SYSTEM_PROMPT,REACT_INSTRUCTION


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
    ):
        self.model=model
        self.memory=memory
        self.skills=skills
        self.max_steps=max_steps

    def _build_react_messages(
        self,
        thread_id:str,
        user_text:str,
        scratchpad:list[AgentStep],
        step_index:int,
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
            '- {"type":"act","skill":"技能名","payload":{...}}\n'
            '- {"type":"final","answer":"..."}'
        )

        return [
            {"role":"system","content":SYSTEM_PROMPT},
            {"role":"system","content":REACT_INSTRUCTION},
            *history,
            {"role":"user","content":user_prompt},
        ]
    
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
        scratchpad:list[AgentStep],
    )->str:
        prompt=(
            f"用户消息：\n{user_text}\n\n"
            f"你已有的中间记录：\n{self._render_scratchpad(scratchpad)}\n\n"
            "你之前没有成功给出最终回答。现在请直接自然地回复用户，不要提技能、工具、JSON、调用过程。"
        )

        raw= await self.model.chat(
            [
                {"role":"system","content":SYSTEM_PROMPT},
                *self.memory.read(thread_id=thread_id),
                {"role":"user","content":prompt},
            ]
        )
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
            if isinstance(skill, str) and skill.strip() and isinstance(payload, dict):
                return {"type": "act", "skill": skill, "payload": payload}
            return {"type": "invalid", "raw": text}
        
        return {"type": "invalid", "raw": text}
    

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

    async def reply(self,message:UniMessage)->str:
        thread_id=message.context.thread_id
        user_text=self._render_user_message_for_agent(message)

        print(user_text)

        scratchpad: list[AgentStep]=[]

        answer=None
        for step_index in range(1,self.max_steps+1):
            llm_messages=self._build_react_messages(
                thread_id=thread_id,
                user_text=user_text,
                scratchpad=scratchpad,
                step_index=step_index,
            )

            raw= await self.model.chat(llm_messages)
            action=self._safe_parse_action(raw)

            if action["type"]=="final":
                answer=action["answer"].strip()
                break

            if action["type"]!="act":
                scratchpad.append(
                    AgentStep(
                        kind="observation",
                        content=f"模型输出了无效动作：{raw.strip()}。你必须只输出合法 JSON。"
                    )
                )
                continue

            skill_name=action.get("skill","")
            payload=action.get("payload",{})
            skill=self.skills.get(skill_name)

            if not skill:
                scratchpad.append(
                    AgentStep(
                        kind="observation",
                        skill_name=skill_name,
                        payload=payload,
                        content=f"技能 {skill_name} 不存在。请从可用技能中重新选择，或直接回答。"
                    )
                )
                continue
            scratchpad.append(
                AgentStep(
                    kind="action",
                    skill_name=skill_name,
                    payload=payload,
                    content=f"调用技能 {skill_name}，参数：{self._json_dumps(payload)}"
                )
            )

            try:
                skill_result=await skill.run(
                    SkillRequest(
                        message=message,
                        context=message.context,
                        payload=payload,
                    )
                )

                observation_text=self._normalize_skill_result(skill_result)
            except Exception as e:
                observation_text=f"技能 {skill_name} 执行失败：{type(e).__name__}: {e}"
            
            scratchpad.append(
                AgentStep(
                    kind="observation",
                    skill_name=skill_name,
                    payload=payload,
                    content=observation_text,
                )
            )

        if not answer:
            answer=await self._fallback_answer(
                thread_id=thread_id,
                user_text=user_text,
                scratchpad=scratchpad,
            )
        
        self.memory.append(thread_id,"user",user_text)
        self.memory.append(thread_id,"assistant",answer)
        return answer



"""
class AgentService:
    def __init__(self, model: ChatModel, memory: ConversationMemory, skills: SkillRegistry):
        self.model = model
        self.memory = memory
        self.skills = skills

    async def reply(self, message: UniMessage) -> str:
        thread_id = message.context.thread_id
        user_text = message.to_llm_text()
        planner_prompt = (
            f"可用技能如下：\n{self.skills.summary()}\n\n"
            f"用户消息：\n{user_text}\n\n"
            "如果只是普通闲聊，直接回答。"
        )
        raw = await self.model.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                *self.memory.read(thread_id, 12),
                {"role": "user", "content": planner_prompt},
            ]
        )
        data = self._safe_parse(raw)
        if data.get("mode") == "skill":
            skill = self.skills.get(data.get("skill", ""))
            if not skill:
                answer = f"我本来想调用技能 {data.get('skill')}，但它当前不存在。"
            else:
                skill_result = await skill.run(
                    SkillRequest(
                        message=message,
                        context=message.context,
                        payload=data.get("payload", {}),
                    )
                )
                rawans = await self.model.chat(
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        *self.memory.read(thread_id, 12),
                        {
                            "role": "user",
                            "content": (
                                f"用户原始消息：{user_text}\n\n"
                                f"你已经获得了处理这个请求所需的结果：\n{skill_result.text}\n\n"
                                "现在请直接自然地回复用户。"
                            ),
                        },
                    ]
                )
                print()
                answer=self._safe_parse(rawans).get("answer") or rawans
        else:
            answer = data.get("answer") or raw

        self.memory.append(thread_id, "user", user_text)
        self.memory.append(thread_id, "assistant", answer)
        return answer

    def _safe_parse(self, text: str) -> dict:
        try:
            return json.loads(text.strip())
        except Exception:
            return {"mode": "direct", "answer": text.strip()}

"""
