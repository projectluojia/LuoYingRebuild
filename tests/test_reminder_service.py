from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from luoying_bot.application.services.reminder_service import ReminderService
from luoying_bot.domain.context import (
    ChannelType,
    ChatContext,
    ConversationTarget,
    Platform,
    UserIdentity,
)
from luoying_bot.infra.scheduler.async_scheduler import ScheduledJob
from luoying_bot.ports.repos import ReminderRecord


def _build_context(*, platform: Platform = Platform.WEB, user_id: str = "u001", group_id: str = "g001") -> ChatContext:
    return ChatContext(
        user=UserIdentity(user_id=user_id, user_name="Tester"),
        target=ConversationTarget(
            channel_type=ChannelType.GROUP if platform == Platform.QQ else ChannelType.WEB,
            conversation_id=group_id,
            platform=platform,
        ),
    )


class _FakeRepo:
    def __init__(self, records: list[ReminderRecord] | None = None) -> None:
        self.records = list(records or [])
        self.saved: list[ReminderRecord] = []
        self.deleted_task_ids: list[list[str]] = []
        self.updated_run_time: list[tuple[str, datetime]] = []

    def list_by_user_and_group(self, user_id: str, group_id: str) -> list[ReminderRecord]:
        return [r for r in self.records if r.user_id == user_id and r.group_id == group_id]

    def list_all(self) -> list[ReminderRecord]:
        return list(self.records)

    def save(self, record: ReminderRecord) -> None:
        self.saved.append(record)
        self.records.append(record)

    def delete_many(self, task_ids: list[str]) -> None:
        self.deleted_task_ids.append(list(task_ids))
        task_id_set = set(task_ids)
        self.records = [r for r in self.records if r.task_id not in task_id_set]

    def update_run_time(self, task_id: str, run_time: datetime) -> None:
        self.updated_run_time.append((task_id, run_time))
        for record in self.records:
            if record.task_id == task_id:
                record.run_time = run_time
                break


class _FakeScheduler:
    def __init__(self) -> None:
        self.added_jobs: list[ScheduledJob] = []
        self.removed_job_ids: list[str] = []

    def add_job(self, job: ScheduledJob) -> None:
        self.added_jobs.append(job)

    def remove_job(self, job_id: str) -> None:
        self.removed_job_ids.append(job_id)


class _FakeTransport:
    def __init__(self) -> None:
        self.sent_text: list[str] = []

    async def send_text(self, context: ChatContext, text: str) -> None:
        self.sent_text.append(text)


def _record(
    *,
    task_id: str,
    user_id: str = "u001",
    group_id: str = "g001",
    run_time: datetime,
    content: str = "喝水",
    platform: Platform = Platform.WEB,
    repeat: bool = False,
) -> ReminderRecord:
    return ReminderRecord(
        task_id=task_id,
        user_id=user_id,
        group_id=group_id,
        run_time=run_time,
        content=content,
        context=_build_context(platform=platform, user_id=user_id, group_id=group_id),
        repeat=repeat,
    )


class ReminderServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_restore_jobs_cleans_expired_non_repeat_and_reschedules_repeat(self) -> None:
        now = datetime.now()
        expired_once = _record(task_id="once-1", run_time=now - timedelta(minutes=10), repeat=False)
        expired_repeat = _record(task_id="repeat-1", run_time=now - timedelta(days=2), repeat=True)
        future_once = _record(task_id="once-2", run_time=now + timedelta(hours=1), repeat=False)

        repo = _FakeRepo([expired_once, expired_repeat, future_once])
        scheduler = _FakeScheduler()
        service = ReminderService(repo=repo, scheduler=scheduler, transport=_FakeTransport())

        await service.restore_jobs()

        self.assertIn(["once-1"], repo.deleted_task_ids)
        self.assertEqual(len(repo.updated_run_time), 1)
        self.assertEqual(repo.updated_run_time[0][0], "repeat-1")
        self.assertGreater(repo.updated_run_time[0][1], now)
        self.assertEqual(len(scheduler.added_jobs), 2)
        self.assertCountEqual([job.job_id for job in scheduler.added_jobs], ["repeat-1", "once-2"])

    async def test_callback_for_non_repeat_sends_and_deletes(self) -> None:
        now = datetime.now()
        record = _record(task_id="job-1", run_time=now, repeat=False, content="提交周报")
        repo = _FakeRepo([record])
        scheduler = _FakeScheduler()
        transport = _FakeTransport()
        service = ReminderService(repo=repo, scheduler=scheduler, transport=transport)

        job = service._build_job(record)
        await job.callback(job)

        self.assertEqual(transport.sent_text, ["提醒：提交周报"])
        self.assertEqual(repo.deleted_task_ids, [["job-1"]])
        self.assertEqual(repo.updated_run_time, [])

    async def test_callback_for_repeat_updates_next_run_time_and_qq_prefix(self) -> None:
        now = datetime.now()
        record = _record(
            task_id="job-2",
            run_time=now,
            repeat=True,
            content="开会",
            platform=Platform.QQ,
            user_id="10001",
        )
        repo = _FakeRepo([record])
        scheduler = _FakeScheduler()
        transport = _FakeTransport()
        service = ReminderService(repo=repo, scheduler=scheduler, transport=transport)

        job = service._build_job(record)
        await job.callback(job)

        self.assertEqual(transport.sent_text, ["[CQ:at,qq=10001] 提醒：开会"])
        self.assertEqual(len(repo.updated_run_time), 1)
        self.assertEqual(repo.updated_run_time[0][0], "job-2")
        self.assertEqual(repo.updated_run_time[0][1], now + timedelta(days=1))
        self.assertEqual(repo.deleted_task_ids, [])

    async def test_create_saves_and_schedules(self) -> None:
        repo = _FakeRepo()
        scheduler = _FakeScheduler()
        transport = _FakeTransport()
        service = ReminderService(repo=repo, scheduler=scheduler, transport=transport)

        run_time = datetime(2026, 3, 23, 9, 30)
        message = await service.create(_build_context(), run_time, "晨会", repeat=False)

        self.assertEqual(message, "已创建提醒：2026-03-23 09:30 - 晨会")
        self.assertEqual(len(repo.saved), 1)
        self.assertEqual(len(scheduler.added_jobs), 1)
        self.assertEqual(scheduler.added_jobs[0].run_time, run_time)

    def test_list_for_user_empty_and_sorted(self) -> None:
        now = datetime.now().replace(second=0, microsecond=0)
        repo = _FakeRepo()
        service = ReminderService(repo=repo, scheduler=_FakeScheduler(), transport=_FakeTransport())

        empty_text = service.list_for_user(_build_context())
        self.assertEqual(empty_text, "当前没有提醒任务")

        late = _record(task_id="2", run_time=now + timedelta(hours=2), content="晚任务")
        early = _record(task_id="1", run_time=now + timedelta(hours=1), content="早任务", repeat=True)
        repo.records.extend([late, early])
        result = service.list_for_user(_build_context())
        self.assertTrue(result.startswith("你的提醒如下："))
        self.assertIn("1. " + early.run_time.strftime("%Y-%m-%d %H:%M") + " - 早任务（每日重复）", result)
        self.assertIn("2. " + late.run_time.strftime("%Y-%m-%d %H:%M") + " - 晚任务", result)

    def test_delete_by_indexes_validates_and_deduplicates(self) -> None:
        now = datetime.now().replace(second=0, microsecond=0)
        r1 = _record(task_id="a", run_time=now + timedelta(minutes=10), content="A")
        r2 = _record(task_id="b", run_time=now + timedelta(minutes=20), content="B")
        repo = _FakeRepo([r1, r2])
        scheduler = _FakeScheduler()
        service = ReminderService(repo=repo, scheduler=scheduler, transport=_FakeTransport())

        self.assertEqual(service.delete_by_indexes(_build_context(), [3]), "编号不存在")
        result = service.delete_by_indexes(_build_context(), [2, 2, 1])
        self.assertTrue(result.startswith("已删除提醒："))
        self.assertIn(" - A", result)
        self.assertIn(" - B", result)
        self.assertEqual(repo.deleted_task_ids[-1], ["a", "b"])
        self.assertEqual(scheduler.removed_job_ids, ["a", "b"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
