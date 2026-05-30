from __future__ import annotations
import asyncio
import heapq
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Dict

from luoying_bot.domain.schedule import ScheduleRule

logger=logging.getLogger(__name__)

@dataclass(slots=True)
class ScheduledJob:
    job_id: str
    run_time: datetime
    callback: Callable[['ScheduledJob'], Awaitable[None]]
    repeat_daily: bool = False
    schedule_rule: ScheduleRule | None = None
    payload: dict | None = None

class AsyncScheduler:
    def __init__(self):
        self.jobs: Dict[str, ScheduledJob] = {}
        self._heap: list[tuple[float, str]] = []
        self._wake_event = asyncio.Event()
        self.running = False

    def add_job(self, job: ScheduledJob) -> None:
        self.jobs[job.job_id] = job
        heapq.heappush(self._heap, (job.run_time.timestamp(), job.job_id))
        self._wake_event.set()

    def remove_job(self, job_id: str) -> None:
        removed = self.jobs.pop(job_id, None)
        if removed is not None:
            self._wake_event.set()

    async def _run_job(self, job: ScheduledJob) -> None:
        try:
            await job.callback(job)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("计划任务执行失败，job_id=%s", job.job_id)

        if not self.running:
            return

        current = self.jobs.get(job.job_id)
        if current is not job:
            logger.warning("计划任务不存在，job_id=%s", job.job_id)
            return
        if job.schedule_rule is not None:
            job.run_time = job.schedule_rule.next_run_after(datetime.now())
            heapq.heappush(self._heap, (job.run_time.timestamp(), job.job_id))
            self._wake_event.set()

        elif job.repeat_daily:
            job.run_time = job.run_time + timedelta(days=1)
            heapq.heappush(self._heap, (job.run_time.timestamp(), job.job_id))
            self._wake_event.set()
        else:
            self.jobs.pop(job.job_id, None)

        logger.info("计划任务执行成功，job_id=%s", job.job_id)

    async def start(self) -> None:
        self.running = True

        while self.running:
            if not self.jobs:
                self._wake_event.clear()
                await self._wake_event.wait()
                continue

            while self._heap:
                ts, job_id = self._heap[0]
                job = self.jobs.get(job_id)
                if job is None:
                    heapq.heappop(self._heap)
                    continue
                if abs(job.run_time.timestamp() - ts) > 0.001:
                    heapq.heappop(self._heap)
                    continue
                break

            if not self._heap:
                continue

            next_ts, _ = self._heap[0]
            delay = max(0, next_ts - datetime.now().timestamp())

            self._wake_event.clear()
            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=delay)
                continue
            except asyncio.TimeoutError:
                pass

            ts, job_id = heapq.heappop(self._heap)
            job = self.jobs.get(job_id)
            if job is None:
                continue
            if abs(job.run_time.timestamp() - ts) > 0.001:
                continue

            asyncio.create_task(self._run_job(job), name=f"scheduled-job:{job_id}")

    def stop(self) -> None:
        self.running = False
        self._wake_event.set()
