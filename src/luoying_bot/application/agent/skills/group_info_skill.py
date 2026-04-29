from __future__ import annotations

import logging

from datetime import datetime
from typing import Any

from luoying_bot.application.agent.skill_base import BaseSkill, SkillRequest, SkillResult
from luoying_bot.domain.context import Platform

logger = logging.getLogger(__name__)

class GroupInfoSkill(BaseSkill):
    name = "group_info"
    platform = [Platform.QQ]
    description = (
        "查询当前群聊结构、完整群成员信息、或指定成员信息。"
        "仅适用于群聊。"
        "payload 支持 mode=summary/full/user/self。 可提供 "
        "mode=summary：返回群名、群号、群主、管理员、机器人、群人数。"
        "mode=full：返回当前群完整成员信息；当群人数超过阈值时拒绝，并自动降级为 summary。"
        "mode=user：查询指定成员信息，必须提供 target_qq。"
        "mode=self：查询当前用户自己的绑定资料，如姓名、学部、学院、年级。"
        "当用户问‘这个群谁是群主’‘管理员有哪些’‘机器人是谁’‘查一下某个QQ’"
        "‘这个人什么学院’‘他什么时候入群’‘他是不是机器人’时优先调用本技能。"
        "如果只是问整个群的大致结构，用 summary；"
        "如果要查某个成员但已经知道 QQ号，用 user；"
        "如果要全量成员清单才用 full；"
        "如果要查询用户自己的信息，用self。"
    )

    DEFAULT_MAX_MEMBER_THRESHOLD = 100

    async def run(self, req: SkillRequest) -> SkillResult:
        context = req.context
        target = getattr(context, "target", None)
        

        if not target or str(getattr(target, "channel_type", "")) not in {"group", "ChannelType.GROUP", "ChannelType.group"}:
            return SkillResult(text="该技能仅支持群聊场景")

        mode = str(req.payload.get("mode") or "summary").strip().lower()

        logger.info("查询群聊信息 Skill，mode=%s", mode)


        if mode == "summary":
            return await self._summary(req)
        if mode == "full":
            return await self._full(req)
        if mode == "user":
            target_qq = str(req.payload.get("target_qq") or "").strip()
            if not target_qq:
                return SkillResult(text="查询指定成员时必须提供 target_qq")
            return await self._query_user(req, target_qq)
        if mode == "self":
            current_qq = str(getattr(getattr(context, "user", None), "user_id", "") or "").strip()
            if not current_qq:
                return SkillResult(text="无法获取当前用户QQ")
            return await self._query_user(req, current_qq)

        return SkillResult(text="不支持的 mode，可用值：summary / full / user / self")

    async def _get_members(self, req: SkillRequest) -> list[dict[str, Any]]:
        runtime = self.services.runtime
        transport = self.services.transport
        group_id = str(req.context.target.conversation_id)

        members = await transport.get_group_members(req.context)
        runtime.member_cache[group_id] = members or []
        return runtime.member_cache.get(group_id, [])

    def _group_name(self, req: SkillRequest) -> str:
        return str(getattr(req.context.target, "group_name", None) or "未知群聊")

    def _group_id(self, req: SkillRequest) -> str:
        return str(req.context.target.conversation_id)

    def _format_ts(self, value: Any) -> str:
        if value in (None, "", 0, "0"):
            return "未知"
        try:
            ts = int(value)
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(value)

    async def _summary(self, req: SkillRequest) -> SkillResult:
        members = await self._get_members(req)
        if not members:
            return SkillResult(text="当前群成员缓存为空，请稍后再试")

        owner = None
        admins: list[tuple[str, str]] = []
        robots: list[tuple[str, str]] = []

        for m in members:
            uid = str(m.get("user_id") or "")
            nickname = str(m.get("nickname") or m.get("card") or "未知")
            role = m.get("role")
            is_robot = bool(m.get("is_robot", False))

            if role == "owner":
                owner = (nickname, uid)
            if role == "admin":
                admins.append((nickname, uid))
            if is_robot:
                robots.append((nickname, uid))

        result: list[str] = []
        result.append(f"群名称：{self._group_name(req)}")
        result.append(f"群号：{self._group_id(req)}")
        result.append(f"群人数：{len(members)}")

        if owner:
            result.append(f"群主：{owner[0]} ({owner[1]})")
        else:
            result.append("群主：未找到")

        if admins:
            admin_str = "，".join(f"{name} ({uid})" for name, uid in admins)
            result.append(f"管理员：{admin_str}")
        else:
            result.append("管理员：无")

        if robots:
            robot_str = "，".join(f"{name} ({uid})" for name, uid in robots)
            result.append(f"机器人：{robot_str}")
        else:
            result.append("机器人：无")

        return SkillResult(
            text="\n".join(result),
            data={
                "group_id": self._group_id(req),
                "group_name": self._group_name(req),
                "member_count": len(members),
            },
        )

    async def _full(self, req: SkillRequest) -> SkillResult:
        members = await self._get_members(req)
        if not members:
            return SkillResult(text="当前群成员缓存为空，请稍后再试")

        threshold = int(req.payload.get("max_member_threshold") or self.DEFAULT_MAX_MEMBER_THRESHOLD)
        member_count = len(members)

        if member_count > threshold:
            summary = await self._summary(req)
            return SkillResult(
                text=(
                    f"当前群人数为 {member_count}，超过安全阈值 {threshold}，拒绝返回完整成员清单。\n"
                    f"已自动返回精简信息：\n\n{summary.text}"
                ),
                data=summary.data,
            )

        result: list[str] = []
        result.append(f"群名称：{self._group_name(req)}")
        result.append(f"群号：{self._group_id(req)}")
        result.append(f"群人数：{member_count}")
        result.append("")
        result.append("======= 成员列表 =======")
        result.append("")

        for m in members:
            info_block = [
                f"QQ号：{m.get('user_id')}",
                f"昵称：{m.get('nickname') or '未知'}",
                f"群名片：{m.get('card') or '无'}",
                f"身份：{m.get('role') or 'member'}",
                f"是否机器人：{bool(m.get('is_robot', False))}",
                f"性别：{m.get('sex') or '未知'}",
                f"年龄：{m.get('age') if m.get('age') not in (None, '') else '未知'}",
                f"等级：{m.get('level') if m.get('level') not in (None, '') else '未知'}",
                f"QQ等级：{m.get('qq_level') if m.get('qq_level') not in (None, '') else '未知'}",
                f"入群时间：{self._format_ts(m.get('join_time'))}",
                f"最后发言时间：{self._format_ts(m.get('last_sent_time'))}",
                f"头衔：{m.get('title') or '无'}",
            ]
            result.append("\n".join(info_block))
            result.append("-" * 30)

        return SkillResult(
            text="\n".join(result),
            data={
                "group_id": self._group_id(req),
                "group_name": self._group_name(req),
                "member_count": member_count,
                "mode": "full",
            },
        )

    async def _query_user(self, req: SkillRequest, target_qq: str) -> SkillResult:
        members = await self._get_members(req)
        if not members:
            return SkillResult(text="当前群成员缓存为空，请稍后再试")

        target_member = None
        for m in members:
            if str(m.get("user_id")) == str(target_qq):
                target_member = m
                break

        if not target_member:
            return SkillResult(text="未找到该成员")

        nickname = target_member.get("nickname") or "未知"
        sex = target_member.get("sex") or "未知"
        card = target_member.get("card") or "无"
        role = target_member.get("role") or "member"
        join_str = self._format_ts(target_member.get("join_time"))
        last_str = self._format_ts(target_member.get("last_sent_time"))
        is_robot = bool(target_member.get("is_robot", False))
        title = target_member.get("title") or "无"

        user_service = self.services.user_service
        user_repo = getattr(user_service, "repo", None)
        profile = user_repo.get(target_qq) if user_repo else None

        college = getattr(profile, "college", None) if profile else None
        year = getattr(profile, "year", None) if profile else None
        department = getattr(profile, "department", None) if profile else None
        real_name = getattr(profile, "name", None) if profile else None

        text = (
            f"QQ号：{target_qq}\n"
            f"昵称：{nickname}\n"
            f"性别：{sex}\n"
            f"群昵称：{card}\n"
            f"群身份（成员、管理、群主）：{role}\n"
            f"群头衔：{title}\n"
            f"入群时间：{join_str}\n"
            f"最近发言时间：{last_str}\n"
            f"是否机器人：{is_robot}\n"
            f"学部：{department or '未登记'}\n"
            f"学院：{college or '未登记'}\n"
            f"入学年份：{year or '未登记'}\n"
            f"姓名：{real_name or '未登记'}"
        )

        return SkillResult(
            text=text,
            data={
                "target_qq": target_qq,
                "nickname": nickname,
                "role": role,
                "is_robot": is_robot,
                "department": department,
                "college": college,
                "year": year,
                "name": real_name,
            },
        )
