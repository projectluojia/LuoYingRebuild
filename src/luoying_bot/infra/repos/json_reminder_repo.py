from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from threading import Lock

from luoying_bot.domain.context import (
    ChatContext,
    ChannelType,
    ConversationTarget,
    Platform,
    UserIdentity,
)
from luoying_bot.domain.schedule import ScheduleRule

from luoying_bot.ports.repos import ReminderRecord, ReminderRepo

#负责存取reminder
class JsonReminderRepo(ReminderRepo):
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        if not self.path.exists():
            self.path.write_text('[]', encoding='utf-8')
    
    
    #读
    def _read(self) -> list[dict]:
        return json.loads(self.path.read_text(encoding='utf-8'))
    
    #写
    def _write(self, data: list[dict]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + '.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(self.path)
    

    #将json解析为数据类
    def _to_record(self, row: dict) -> ReminderRecord:
        context_data=row.get('context')
        context=ChatContext.from_dict(context_data)
        
        return ReminderRecord(
            task_id=row['task_id'], 
            user_id=row['user_id'], 
            group_id=row['group_id'], 
            run_time=datetime.strptime(row['run_time'], '%Y-%m-%d %H:%M'), 
            content=row['content'], 
            context=context,
            repeat=row.get('repeat', False),
            schedule_rule=ScheduleRule.from_dict(row.get('schedule_rule')),
        )
    
    #依照群组和个人查询事件
    def list_by_user_and_group(self, user_id: str, group_id: str) -> list[ReminderRecord]:
        return [
            self._to_record(row)
            for row in self._read() 
            if row['user_id']==user_id and row['group_id']==group_id
        ]
    
    #列出全局所有事件
    def list_all(self) -> list[ReminderRecord]:
        return [self._to_record(row) for row in self._read()]

    #持久化事件 
    def save(self, record: ReminderRecord) -> None:
        with self._lock:
            data = self._read()
            data.append(
                {
                    'task_id': record.task_id, 
                    'user_id': record.user_id, 
                    'group_id': record.group_id, 
                    'run_time': record.run_time.strftime('%Y-%m-%d %H:%M'), 
                    'content': record.content, 
                    'repeat': record.repeat,
                    'schedule_rule': record.schedule_rule.to_dict() if record.schedule_rule else None,
                    'context': record.context.to_dict(),
                }
            )
            self._write(data)
    
    #删除多个事件
    def delete_many(self, task_ids: list[str]) -> None:
        with self._lock:
            data = [row for row in self._read() if row['task_id'] not in set(task_ids)]
            self._write(data)
    
    #更新事件的运行时间
    def update_run_time(self, task_id: str, run_time: datetime) -> None:
        with self._lock:
            data = self._read()
            for row in data:
                if row['task_id'] == task_id:
                    row['run_time'] = run_time.strftime('%Y-%m-%d %H:%M')
                    break
            self._write(data)
