from __future__ import annotations

from datetime import datetime

from luoying_bot.domain.schedule import ScheduleRule
from luoying_bot.application.jobs.builtin_jobs import BUILTIN_JOBS, BuiltinJobSpec
from luoying_bot.application.services.group_runtime import GroupRuntime
from luoying_bot.domain.context import (
    ChannelType,
    ChatContext,
    ConversationTarget,
    Platform,
    UserIdentity,
)
from luoying_bot.infra.scheduler.async_scheduler import AsyncScheduler, ScheduledJob
from luoying_bot.ports.transport import ChatTransport


# 内置计划事件服务
class BuiltinScheduleService:
    def __init__(
        self,
        scheduler: AsyncScheduler,
        transport: ChatTransport,
        runtime: GroupRuntime,
    ):
        self.scheduler = scheduler
        self.transport = transport
        self.runtime = runtime

    # 注册所有内置计划事件
    def register_builtin_jobs(self) -> None:
        for group_id, enabled in self.runtime.enabled_groups.items():
            if not enabled:
                continue

            for spec in BUILTIN_JOBS:
                if not spec.enabled:
                    continue

                job = self._build_job(group_id, spec)
                self.scheduler.add_job(job)

    def _build_rule(self, spec: BuiltinJobSpec) -> ScheduleRule:
        return ScheduleRule(
            hour=spec.hour,
            minute=spec.minute,
            weekly_days=spec.weekly_days,
            month_days=spec.month_days,
            union_weekly_monthly=spec.union_weekly_monthly,
        )

    # 构造真正可交给 scheduler 的 job
    def _build_job(self, group_id: str, spec: BuiltinJobSpec) -> ScheduledJob:
        job_id = f'builtin:{spec.job_key}:group:{group_id}'
        rule = self._build_rule(spec)
        run_time = rule.next_run_after(datetime.now())

        async def callback(job: ScheduledJob) -> None:
            await spec.handler(self, group_id, job)

        return ScheduledJob(
            job_id=job_id,
            run_time=run_time,
            callback=callback,
            schedule_rule=rule,
            payload={
                'group_id': group_id,
                'job_key': spec.job_key,
                "schedule_rule": rule.to_dict(),
            },
        )

    # 为内置任务构造群消息上下文
    def build_group_context(self, group_id: str) -> ChatContext:
        return ChatContext(
            user=UserIdentity(
                user_id='0',
                user_name='builtin_scheduler',
            ),
            target=ConversationTarget(
                channel_type=ChannelType.GROUP,
                conversation_id=str(group_id),
                platform=Platform.QQ,
            ),
            message_id=None,
            request_uid=f'builtin:{group_id}',
        )

    # 内置任务常用能力：给群发文本
    async def send_group_text(self, group_id: str, text: str) -> None:
        ctx = self.build_group_context(group_id)
        await self.transport.send_text(ctx, text)
