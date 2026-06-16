from __future__ import annotations

import logging

from luoying_bot.application.agent.skill_base import BaseSkill, SkillRequest, SkillResult
from luoying_bot.domain.context import Platform

logger = logging.getLogger(__name__)


class KnowledgeSkill(BaseSkill):
    name = "knowledge"
    platform = [Platform.QQ, Platform.WEB, Platform.CLI]
    description = (
        "操作全局知识库。"
        "支持 action=list/add/search/summary/delete/clear。"
        "其中 add、delete、clear 为写操作，仅管理员可用；list、search、summary 所有用户可用。"
        "如果非管理员用户要求添加、删除或清空知识库，应直接告知权限不足，不要尝试调用。"
        "常见 payload："
        '{"action":"list"} '
        '{"action":"add","title":"标题","content":"内容","tags":["标签1"],"source":"来源URL"} '
        '{"action":"search","keyword":"关键词"} '
        '{"action":"summary"} '
        '{"action":"delete","id":"kb_001"} '
        '{"action":"clear"}'
    )

    _WRITE_ACTIONS = {"add", "delete", "clear"}

    async def run(self, req: SkillRequest) -> SkillResult:
        svc = self.services.knowledge_service
        action = (req.payload.get("action") or "list").strip().lower()

        if action in self._WRITE_ACTIONS:
            user_id = str(req.context.user.user_id)
            if user_id not in self.services.ops:
                return SkillResult(
                    text="权限不足，知识库写操作仅限管理员",
                    data={"ok": False, "action": action},
                )

        try:
            if action == "list":
                logger.info("知识库 list 请求")
                result = svc.list_items()

            elif action == "add":
                logger.info("知识库 add 请求")
                result = svc.add_item(
                    title=req.payload.get("title", ""),
                    content=req.payload.get("content", ""),
                    tags=self._to_tags(req.payload.get("tags")),
                    source=req.payload.get("source", ""),
                )

            elif action == "search":
                logger.info("知识库 search 请求")
                result = svc.search_items(
                    keyword=req.payload.get("keyword", ""),
                )

            elif action == "summary":
                logger.info("知识库 summary 请求")
                result = await svc.generate_summary()

            elif action == "delete":
                logger.info("知识库 delete 请求")
                result = svc.delete_item(
                    item_id=req.payload.get("id"),
                )

            elif action == "clear":
                logger.info("知识库 clear 请求")
                result = svc.clear_all()

            else:
                return SkillResult(
                    text=f"不支持的知识库 action：{action}",
                    data={"ok": False, "action": action},
                )

            return SkillResult(
                text=result.text,
                data={
                    "ok": result.ok,
                    "action": action,
                    **result.data,
                },
            )

        except Exception as e:
            return SkillResult(
                text=f"知识库操作失败：{type(e).__name__}: {e}",
                data={"ok": False, "action": action},
            )

    def _to_tags(self, value, allow_none: bool = False):
        if value is None:
            return None if allow_none else []
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            return [x.strip() for x in text.split(",") if x.strip()]
        return []
