from __future__ import annotations
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Dict

#这个文件是一个异步调度器
#提醒系统的核心

#一个计划事件
@dataclass(slots=True)
class ScheduledJob:
    job_id: str
    run_time: datetime
    callback: Callable[['ScheduledJob'], Awaitable[None]]
    repeat_daily: bool = False
    payload: dict | None = None

class AsyncScheduler:
    def __init__(self):
        self.jobs: Dict[str, ScheduledJob] = {}
        self.running = False

    #添加一个计划事件
    def add_job(self, job: ScheduledJob) -> None:
        self.jobs[job.job_id] = job
    
    #删除一个计划事件
    def remove_job(self, job_id: str) -> None:
        self.jobs.pop(job_id, None)
    
    #开始运行异步调度
    async def start(self) -> None:
        self.running = True
        while self.running:
            now = datetime.now()
            to_remove: list[str] = []
            for job_id, job in list(self.jobs.items()):
                if now >= job.run_time:
                    await job.callback(job)
                    if job.repeat_daily:
                        job.run_time = job.run_time + timedelta(days=1)
                    else:
                        to_remove.append(job_id)
            for job_id in to_remove:
                self.remove_job(job_id)
            await asyncio.sleep(1)
    
    #停止运行异步调度
    def stop(self) -> None:
        self.running = False
