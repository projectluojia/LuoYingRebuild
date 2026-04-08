from __future__ import annotations

from luoying_bot.application.agent.skill_base import BaseSkill, SkillRequest, SkillResult
from luoying_bot.domain.context import Platform


class UserMemorySkill(BaseSkill):
    name = "user_memory"
    platform = [Platform.QQ, Platform.WEB]
    description = (
        "读取或修改当前用户的长期记忆。长期记忆只是一小段用户简介。"
        "当用户明确要求“记住/更新记忆/忘记”时，可以修改。"
        "当你认为确实需要记住用户的喜好、兴趣时，也可以修改"
        '常见 payload：'
        '{"action":"read"} '
        '{"action":"write","content":"用户是武大AI学院学生，喜欢一步一步讲解。"} '
        '{"action":"clear"}'
        "如果要更新，建议先 read，再 write，把完整新内容覆盖写回。"
    )

    async def run(self, req: SkillRequest) -> SkillResult:
        svc = self.services.user_memory_service
        user_id = str(req.context.user.user_id)
        action = (req.payload.get("action") or "read").strip().lower()

        if action in {"read", "get"}:
            result = svc.get_memory(user_id)
            return SkillResult(text=result.text, data=result.data)

        if action in {"write", "set", "update", "overwrite"}:
            content = str(req.payload.get("content") or "").strip()
            result = svc.set_memory(user_id, content)
            return SkillResult(text=result.text, data=result.data)

        if action in {"clear", "delete", "forget"}:
            result = svc.clear_memory(user_id)
            return SkillResult(text=result.text, data=result.data)

        return SkillResult(text=f"不支持的 user_memory action: {action}")