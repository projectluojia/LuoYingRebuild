from __future__ import annotations

import logging

from datetime import datetime, timedelta
import uuid

from luoying_bot.domain.context import ChatContext
from luoying_bot.infra.scheduler.async_scheduler import AsyncScheduler, ScheduledJob
from luoying_bot.ports.repos import ReminderRecord, ReminderRepo
from luoying_bot.ports.transport import ChatTransport

#提醒服务
class ReminderService:
    def __init__(self, repo: ReminderRepo, scheduler: AsyncScheduler, transport: ChatTransport):
        self.repo = repo #持久化仓库
        self.scheduler = scheduler #运行器
        self.transport = transport#平台

    #恢复所有的job
    async def restore_jobs(self) -> None:
        now = datetime.now()
        for record in self.repo.list_all():

            if not record.repeat and record.run_time <= now:
                self.repo.delete_many([record.task_id])
                continue
            
            if record.repeat and record.run_time <= now:
                next_time = record.run_time
                while next_time <= now:
                    next_time += timedelta(days=1)
                self.repo.update_run_time(record.task_id, next_time)
                record.run_time = next_time

            self.scheduler.add_job(self._build_job(record))


    #建立一个空job
    def _build_job(self, record: ReminderRecord) -> ScheduledJob:
        async def callback(job: ScheduledJob) -> None:
            ctx = record.context
            prefix = self.transport.format_mention(ctx, record.user_id)
            await self.transport.send_text(ctx, f'{prefix}提醒：{record.content}')
            if record.repeat:
                next_time = record.run_time + timedelta(days=1)
                self.repo.update_run_time(record.task_id, next_time)
                record.run_time = next_time
            else:
                self.repo.delete_many([record.task_id])

        return ScheduledJob(
            job_id=record.task_id,
            run_time=record.run_time,
            callback=callback,
            repeat_daily=record.repeat,
            payload={
                'context': record.context.to_dict()
            },
        )

    async def create(self, context: ChatContext, run_time: datetime, content: str, repeat: bool = False) -> str:
        
        record = ReminderRecord(
            task_id=str(uuid.uuid4()),
            user_id=context.user.user_id,
            group_id=context.target.conversation_id,
            run_time=run_time,
            content=content,
            context=context,
            repeat=repeat,
        )
        #持久化
        self.repo.save(record)
        #内存化
        job = self._build_job(record)
        #加进内存
        self.scheduler.add_job(job)
        
        return f"已创建提醒：{run_time.strftime('%Y-%m-%d %H:%M')} - {content}"

    #为用户列出提醒
    def list_for_user(self, context: ChatContext) -> str:
        items = sorted(
            self.repo.list_by_user_and_group(context.user.user_id, context.target.conversation_id),
            key=lambda x: x.run_time,
        )
        if not items:
            return '当前没有提醒任务'
        lines = ['你的提醒如下：']
        for idx, item in enumerate(items, 1):
            lines.append(
                f"{idx}. {item.run_time.strftime('%Y-%m-%d %H:%M')} - {item.content}{'（每日重复）' if item.repeat else ''}"
            )
        return '\n'.join(lines)

    #按编号删除提醒
    def delete_by_indexes(self, context: ChatContext, indexes: list[int]) -> str:
        items = sorted(
            self.repo.list_by_user_and_group(context.user.user_id, context.target.conversation_id),
            key=lambda x: x.run_time,
        )
        if not items:
            return '当前没有提醒任务'
        for idx in indexes:
            if idx < 1 or idx > len(items):
                return '编号不存在'
        targets = [items[idx - 1] for idx in sorted(set(indexes))]
        task_ids = [item.task_id for item in targets]
        self.repo.delete_many(task_ids)
        for tid in task_ids:
            self.scheduler.remove_job(tid)
        return '已删除提醒：\n' + '\n'.join(
            f"{item.run_time.strftime('%Y-%m-%d %H:%M')} - {item.content}" for item in targets
        )
