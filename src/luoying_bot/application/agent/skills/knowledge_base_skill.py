from __future__ import annotations

from luoying_bot.application.agent.skill_base import (
    BaseSkill,
    SkillRequest,
    SkillResult,
)
from luoying_bot.domain.context import Platform


class KnowledgeBaseSkill(BaseSkill):
    name = "knowledge_base"
    platform = [Platform.QQ, Platform.WEB, Platform.CLI]
    description = (
        "查询学校知识库。适合回答招生、政策、专业介绍、办事说明、学校资料等需要可靠来源的问题。"
        "本技能使用 Git 管理的网页 Markdown artifact 和本地混合索引。"
        "回答正文不需要包含来源；系统会把本技能返回的来源链接附在最终回复末尾。"
        "没有可靠来源时会拒绝给出确定结论。"
        "payload 示例："
        '{"question":"去年河北物理类人工智能最低多少分？"} '
        '{"question":"软件工程和人工智能专业有什么区别？"}'
    )

    async def run(self, req: SkillRequest) -> SkillResult:
        question = req.message.to_llm_text().strip() or req.message.get_plain_text().strip()
        if not question:
            return SkillResult(
                text="知识库查询问题不能为空",
                data={"ok": False},
            )

        context = req.context
        answer = await self.services.knowledge_base_service.answer(
            question=question,
            platform=context.target.platform.value,
            conversation_id=context.target.conversation_id,
            user_id=context.user.user_id,
            filters=self._dict_payload(req.payload.get("filters")),
            top_k=self._top_k(req.payload.get("top_k")),
            request_uid=context.request_uid,
        )
        if answer.fallback_reason is not None:
            observation = (
                "知识库没有找到可直接回答该问题的可靠材料。"
                f"fallback_reason={answer.fallback_reason}。"
                "请不要把知识库拒答文案直接发给用户；可以尝试其他技能，"
                "或基于已有上下文给出非知识库结论并说明不确定性。"
            )
            return SkillResult(
                text=observation,
                data={
                    "ok": False,
                    **answer.to_dict(),
                },
                llm_observation=observation,
                final_response=False,
            )
        return SkillResult(
            text=answer.answer,
            data={
                "ok": True,
                **answer.to_dict(),
            },
            metadata={"skip_output_risk_control": bool(answer.citations)},
            llm_observation=answer.answer,
            final_append_text=answer.source_links_text(),
            final_response=True,
        )

    def _dict_payload(self, value) -> dict:
        return dict(value) if isinstance(value, dict) else {}

    def _top_k(self, value) -> int:
        try:
            top_k = int(value)
        except (TypeError, ValueError):
            return 8
        return max(1, min(top_k, 20))
