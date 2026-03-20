from __future__ import annotations

from datetime import datetime, timedelta

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

    # 构造真正可交给 scheduler 的 job
    def _build_job(self, group_id: str, spec: BuiltinJobSpec) -> ScheduledJob:
        job_id = f'builtin:{spec.job_key}:group:{group_id}'
        run_time = self._get_next_run_time(spec.hour, spec.minute)

        async def callback(job: ScheduledJob) -> None:
            await spec.handler(self, group_id, job)

        return ScheduledJob(
            job_id=job_id,
            run_time=run_time,
            callback=callback,
            repeat_daily=True,
            payload={
                'group_id': group_id,
                'job_key': spec.job_key,
            },
        )

    # 计算下次执行时间
    def _get_next_run_time(self, hour: int, minute: int) -> datetime:
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target

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