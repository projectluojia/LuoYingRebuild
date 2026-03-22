from __future__ import annotations

from luoying_bot.application.agent.skill_base import BaseSkill, SkillRequest, SkillResult


class SessionPolicySkill(BaseSkill):
    name = "session_policy"
    description = (
        "查看会话策略与 Web 会话状态。"
        "payload 支持 action=status/list/create/touch_current，"
        "create 可选 title。"
    )

    async def run(self, req: SkillRequest) -> SkillResult:
        action = str(req.payload.get("action") or "status").strip().lower()
        transport = self.services.get("transport")
        policy = self.services.get("session_policy", {})
        scope = (
            transport.resolve_session_scope(req.context)
            if transport and hasattr(transport, "resolve_session_scope")
            else req.context.thread_id
        )

        if action == "status":
            return SkillResult(
                text=(
                    f"当前会话策略：\n"
                    f"- scope: {scope}\n"
                    f"- session_id: {req.context.target.conversation_id}\n"
                    f"- user_id: {req.context.user.user_id}\n"
                    f"- history_window: {policy.get('history_window', 'n/a')}\n"
                    f"- max_sessions_per_user: {policy.get('max_sessions_per_user', 'n/a')}\n"
                    f"- auto_create_web_session: {policy.get('auto_create_web_session', 'n/a')}"
                ),
                data={"scope": scope, "policy": policy},
            )

        store = self.services.get("web_session_store")
        if store is None:
            return SkillResult(text="当前运行模式未启用 Web 会话存储")

        if action == "list":
            sessions = store.list_sessions(user_id=req.context.user.user_id)
            if not sessions:
                return SkillResult(text="当前用户还没有会话")
            lines = ["会话列表："]
            for idx, item in enumerate(sessions[:20], 1):
                lines.append(
                    f"{idx}. {item['session_id']} | {item.get('title', '新会话')} | "
                    f"{item.get('message_count', 0)} 条"
                )
            return SkillResult(text="\n".join(lines), data={"count": len(sessions)})

        if action == "create":
            title = str(req.payload.get("title") or "新会话")
            session = store.create_session(
                user_id=req.context.user.user_id,
                user_name=req.context.user.user_name or req.context.user.user_id,
                title=title,
            )
            return SkillResult(
                text=f"已创建会话：{session['session_id']}（{session['title']}）",
                data={"session": session},
            )

        if action == "touch_current":
            session = store.ensure_session(
                session_id=req.context.target.conversation_id,
                user_id=req.context.user.user_id,
                user_name=req.context.user.user_name or req.context.user.user_id,
            )
            return SkillResult(
                text=f"当前会话已确认：{session['session_id']}（{session['title']}）",
                data={"session": session},
            )

        return SkillResult(text=f"不支持的 session_policy action：{action}")
