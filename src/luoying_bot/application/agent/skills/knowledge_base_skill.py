from __future__ import annotations

from luoying_bot.application.agent.skill_base import BaseSkill, SkillRequest, SkillResult
from luoying_bot.domain.context import Platform


class KnowledgeBaseSkill(BaseSkill):
    name = "knowledge_base"
    platform = [Platform.QQ, Platform.WEB, Platform.CLI]
    description = (
        "查询学校知识库。适合回答招生、政策、专业介绍、办事说明、学校资料等需要可靠来源的问题。"
        "本技能只使用 RAGFlow 和 Directus 中的正式知识，不读取本地旧知识库。"
        "回答会附带来源；没有可靠来源时会拒绝给出确定结论。"
        "payload 示例："
        '{"question":"去年河北物理类人工智能最低多少分？","domain":"admissions","space_id":"admissions"} '
        '{"question":"软件工程和人工智能专业有什么区别？","domain":"admissions"}'
    )

    async def run(self, req: SkillRequest) -> SkillResult:
        question = str(req.payload.get("question") or "").strip()
        if not question:
            question = req.message.to_llm_text().strip() or req.message.get_plain_text().strip()
        if not question:
            return SkillResult(
                text="知识库查询问题不能为空",
                data={"ok": False},
            )

        context = req.context
        answer = await self.services.knowledge_base_service.answer(
            question=question,
            space_id=self._optional_text(req.payload.get("space_id")),
            domain=self._optional_text(req.payload.get("domain")),
            platform=context.target.platform.value,
            conversation_id=context.target.conversation_id,
            user_id=context.user.user_id,
            filters=self._dict_payload(req.payload.get("filters")),
            top_k=self._top_k(req.payload.get("top_k")),
            request_uid=context.request_uid,
        )
        return SkillResult(
            text=answer.text_with_citations(),
            data={
                "ok": answer.fallback_reason is None,
                **answer.to_dict(),
            },
        )

    def _optional_text(self, value) -> str | None:
        text = str(value or "").strip()
        return text or None

    def _dict_payload(self, value) -> dict:
        return dict(value) if isinstance(value, dict) else {}

    def _top_k(self, value) -> int:
        try:
            top_k = int(value)
        except (TypeError, ValueError):
            return 8
        return max(1, min(top_k, 20))

