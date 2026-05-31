from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any, Iterator, Optional

from luoying_bot.domain.context import ChatContext
from luoying_bot.domain.schedule import ScheduleRule
from luoying_bot.ports.repos import (
    MemoItem,
    MemoRepo,
    ReminderRecord,
    ReminderRepo,
    UserMemoryRepo,
    UserProfile,
    UserPromptSettings,
    UserPromptSettingsRepo,
    UserRepo,
)


class SqliteUserDataStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    department TEXT,
                    college TEXT,
                    year TEXT,
                    name TEXT
                );

                CREATE TABLE IF NOT EXISTS user_prompt_settings (
                    user_id TEXT PRIMARY KEY,
                    basic_style TEXT NOT NULL DEFAULT '默认',
                    extra_trait_levels TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS user_memories (
                    user_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memos (
                    user_id TEXT NOT NULL,
                    memo_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (user_id, memo_id)
                );
                CREATE INDEX IF NOT EXISTS idx_memos_user_position
                    ON memos(user_id, position);

                CREATE TABLE IF NOT EXISTS reminders (
                    task_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    run_time TEXT NOT NULL,
                    content TEXT NOT NULL,
                    repeat INTEGER NOT NULL DEFAULT 0,
                    schedule_rule TEXT,
                    context TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_reminders_user_group
                    ON reminders(user_id, group_id);
                CREATE INDEX IF NOT EXISTS idx_reminders_run_time
                    ON reminders(run_time);
                """
            )

    def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT user_id, department, college, year, name
                FROM user_profiles
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return UserProfile(
            user_id=str(row["user_id"]),
            department=row["department"],
            college=row["college"],
            year=row["year"],
            name=row["name"],
        )

    def create_user_profile(self, profile: UserProfile) -> None:
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO user_profiles(user_id, department, college, year, name)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        profile.user_id,
                        profile.department,
                        profile.college,
                        profile.year,
                        profile.name,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("User already exist") from exc

    def update_user_profile_fields(self, user_id: str, **fields: str | None) -> None:
        allowed_fields = {"department", "college", "year", "name"}
        updates = [
            (key, value)
            for key, value in fields.items()
            if key in allowed_fields and value is not None
        ]
        with self._lock, self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM user_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if exists is None:
                raise ValueError("User not exist")
            for key, value in updates:
                conn.execute(
                    f"UPDATE user_profiles SET {key} = ? WHERE user_id = ?",
                    (value, user_id),
                )

    def delete_user_profile(self, user_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM user_profiles WHERE user_id = ?",
                (user_id,),
            )
            return cursor.rowcount > 0

    def get_prompt_settings(self, user_id: str) -> UserPromptSettings | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT user_id, basic_style, extra_trait_levels
                FROM user_prompt_settings
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        extra_trait_levels = self._json_loads(row["extra_trait_levels"], {})
        if not isinstance(extra_trait_levels, dict):
            extra_trait_levels = {}
        return UserPromptSettings(
            user_id=str(row["user_id"]),
            basic_style=str(row["basic_style"] or "默认"),
            extra_trait_levels={str(k): str(v) for k, v in extra_trait_levels.items()},
        )

    def save_prompt_settings(self, settings: UserPromptSettings) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_prompt_settings(user_id, basic_style, extra_trait_levels)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    basic_style = excluded.basic_style,
                    extra_trait_levels = excluded.extra_trait_levels
                """,
                (
                    settings.user_id,
                    settings.basic_style,
                    json.dumps(settings.extra_trait_levels, ensure_ascii=False),
                ),
            )

    def delete_prompt_settings(self, user_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM user_prompt_settings WHERE user_id = ?",
                (user_id,),
            )
            return cursor.rowcount > 0

    def get_memory(self, user_id: str) -> str:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT content FROM user_memories WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return "" if row is None else str(row["content"] or "").strip()

    def set(self, user_id: str, content: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_memories(user_id, content, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    content = excluded.content,
                    updated_at = excluded.updated_at
                """,
                (user_id, (content or "").strip(), self._now()),
            )

    def clear(self, user_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "DELETE FROM user_memories WHERE user_id = ?",
                (user_id,),
            )

    def list_items(self, user_id: str) -> list[MemoItem]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT memo_id, content, tags, created_at, updated_at
                FROM memos
                WHERE user_id = ?
                ORDER BY position ASC, created_at ASC, memo_id ASC
                """,
                (user_id,),
            ).fetchall()
        return [
            MemoItem(
                id=str(row["memo_id"]),
                content=str(row["content"]),
                tags=self._normalize_tags(self._json_loads(row["tags"], [])),
                created_at=str(row["created_at"] or ""),
                updated_at=str(row["updated_at"] or ""),
            )
            for row in rows
        ]

    def save_items(self, user_id: str, items: list[MemoItem]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM memos WHERE user_id = ?", (user_id,))
            conn.executemany(
                """
                INSERT INTO memos(
                    user_id, memo_id, position, content, tags, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        user_id,
                        item.id,
                        index,
                        item.content,
                        json.dumps(item.tags, ensure_ascii=False),
                        item.created_at,
                        item.updated_at,
                    )
                    for index, item in enumerate(items)
                ],
            )

    def list_by_user_and_group(self, user_id: str, group_id: str) -> list[ReminderRecord]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM reminders
                WHERE user_id = ? AND group_id = ?
                ORDER BY run_time ASC, task_id ASC
                """,
                (user_id, group_id),
            ).fetchall()
        return [self._to_reminder_record(row) for row in rows]

    def list_all(self) -> list[ReminderRecord]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM reminders ORDER BY run_time ASC, task_id ASC"
            ).fetchall()
        return [self._to_reminder_record(row) for row in rows]

    def save_reminder(self, record: ReminderRecord) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reminders(
                    task_id, user_id, group_id, run_time, content,
                    repeat, schedule_rule, context
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    user_id = excluded.user_id,
                    group_id = excluded.group_id,
                    run_time = excluded.run_time,
                    content = excluded.content,
                    repeat = excluded.repeat,
                    schedule_rule = excluded.schedule_rule,
                    context = excluded.context
                """,
                (
                    record.task_id,
                    record.user_id,
                    record.group_id,
                    self._datetime_to_db(record.run_time),
                    record.content,
                    1 if record.repeat else 0,
                    json.dumps(record.schedule_rule.to_dict(), ensure_ascii=False)
                    if record.schedule_rule
                    else None,
                    json.dumps(record.context.to_dict(), ensure_ascii=False),
                ),
            )

    def delete_many(self, task_ids: list[str]) -> None:
        if not task_ids:
            return
        placeholders = ",".join("?" for _ in task_ids)
        with self._lock, self._connect() as conn:
            conn.execute(
                f"DELETE FROM reminders WHERE task_id IN ({placeholders})",
                tuple(task_ids),
            )

    def update_run_time(self, task_id: str, run_time: datetime) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE reminders SET run_time = ? WHERE task_id = ?",
                (self._datetime_to_db(run_time), task_id),
            )

    def migrate_from_legacy_paths(
        self,
        *,
        user_db_file: Path,
        user_prompt_settings_file: Path,
        user_memory_dir: Path,
        memo_dir: Path,
        reminder_db_file: Path,
    ) -> None:
        with self._lock, self._connect() as conn:
            self._migrate_user_profiles(conn, user_db_file)
            self._migrate_prompt_settings(conn, user_prompt_settings_file)
            self._migrate_user_memories(conn, user_memory_dir)
            self._migrate_memos(conn, memo_dir)
            self._migrate_reminders(conn, reminder_db_file)

    def _migrate_user_profiles(self, conn: sqlite3.Connection, path: Path) -> None:
        data = self._read_json_file(path, {})
        if not isinstance(data, dict):
            return
        for user_id, row in data.items():
            if not isinstance(row, dict):
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO user_profiles(user_id, department, college, year, name)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(user_id),
                    row.get("department"),
                    row.get("college"),
                    row.get("year"),
                    row.get("name"),
                ),
            )

    def _migrate_prompt_settings(self, conn: sqlite3.Connection, path: Path) -> None:
        data = self._read_json_file(path, {})
        if not isinstance(data, dict):
            return
        for user_id, row in data.items():
            if not isinstance(row, dict):
                continue
            extra_trait_levels = row.get("extra_trait_levels", {})
            if not isinstance(extra_trait_levels, dict):
                extra_trait_levels = {}
            conn.execute(
                """
                INSERT OR IGNORE INTO user_prompt_settings(
                    user_id, basic_style, extra_trait_levels
                )
                VALUES (?, ?, ?)
                """,
                (
                    str(user_id),
                    str(row.get("basic_style") or "默认"),
                    json.dumps(extra_trait_levels, ensure_ascii=False),
                ),
            )

    def _migrate_user_memories(self, conn: sqlite3.Connection, memory_dir: Path) -> None:
        if not memory_dir.exists() or not memory_dir.is_dir():
            return
        for path in sorted(memory_dir.glob("*.txt")):
            try:
                content = path.read_text(encoding="utf-8").strip()
            except Exception:
                continue
            if not content:
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO user_memories(user_id, content, updated_at)
                VALUES (?, ?, ?)
                """,
                (path.stem, content, self._now()),
            )

    def _migrate_memos(self, conn: sqlite3.Connection, memo_dir: Path) -> None:
        if not memo_dir.exists() or not memo_dir.is_dir():
            return
        for path in sorted(memo_dir.glob("memo_*.json")):
            data = self._read_json_file(path, {})
            if not isinstance(data, dict):
                continue
            user_id = str(data.get("user_id") or path.stem.removeprefix("memo_"))
            exists = conn.execute(
                "SELECT 1 FROM memos WHERE user_id = ? LIMIT 1",
                (user_id,),
            ).fetchone()
            if exists is not None:
                continue
            items = data.get("items", [])
            if not isinstance(items, list):
                continue
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                conn.execute(
                    """
                    INSERT OR IGNORE INTO memos(
                        user_id, memo_id, position, content, tags, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        str(item.get("id") or f"m_{index + 1:03d}"),
                        index,
                        str(item.get("content") or ""),
                        json.dumps(self._normalize_tags(item.get("tags")), ensure_ascii=False),
                        str(item.get("created_at") or ""),
                        str(item.get("updated_at") or ""),
                    ),
                )

    def _migrate_reminders(self, conn: sqlite3.Connection, path: Path) -> None:
        data = self._read_json_file(path, [])
        if not isinstance(data, list):
            return
        for row in data:
            if not isinstance(row, dict):
                continue
            task_id = str(row.get("task_id") or "")
            if not task_id:
                continue
            context = row.get("context")
            if not isinstance(context, dict):
                continue
            run_time = self._parse_datetime(str(row.get("run_time") or ""))
            if run_time is None:
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO reminders(
                    task_id, user_id, group_id, run_time, content,
                    repeat, schedule_rule, context
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    str(row.get("user_id") or ""),
                    str(row.get("group_id") or ""),
                    self._datetime_to_db(run_time),
                    str(row.get("content") or ""),
                    1 if row.get("repeat", False) else 0,
                    json.dumps(row.get("schedule_rule"), ensure_ascii=False)
                    if row.get("schedule_rule") is not None
                    else None,
                    json.dumps(context, ensure_ascii=False),
                ),
            )

    def _to_reminder_record(self, row: sqlite3.Row) -> ReminderRecord:
        context_data = self._json_loads(row["context"], {})
        run_time = self._parse_datetime(str(row["run_time"]))
        if run_time is None:
            raise ValueError(f"Invalid reminder run_time: {row['run_time']}")
        return ReminderRecord(
            task_id=str(row["task_id"]),
            user_id=str(row["user_id"]),
            group_id=str(row["group_id"]),
            run_time=run_time,
            content=str(row["content"]),
            context=ChatContext.from_dict(context_data),
            repeat=bool(row["repeat"]),
            schedule_rule=ScheduleRule.from_dict(self._json_loads(row["schedule_rule"], None)),
        )

    def _json_loads(self, value: Any, default: Any) -> Any:
        if value is None:
            return default
        try:
            return json.loads(value)
        except Exception:
            return default

    def _read_json_file(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def _normalize_tags(self, tags: Any) -> list[str]:
        if not isinstance(tags, list):
            return []
        return [str(tag) for tag in tags]

    def _parse_datetime(self, value: str) -> datetime | None:
        for parser in (
            datetime.fromisoformat,
            lambda text: datetime.strptime(text, "%Y-%m-%d %H:%M"),
            lambda text: datetime.strptime(text, "%Y-%m-%d %H:%M:%S"),
        ):
            try:
                return parser(value)
            except Exception:
                continue
        return None

    def _datetime_to_db(self, value: datetime) -> str:
        return value.strftime("%Y-%m-%d %H:%M")

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class SqliteUserRepo(UserRepo):
    def __init__(self, store: SqliteUserDataStore):
        self.store = store

    def get(self, user_id: str) -> Optional[UserProfile]:
        return self.store.get_user_profile(user_id)

    def create(self, profile: UserProfile) -> None:
        self.store.create_user_profile(profile)

    def update_fields(self, user_id: str, **fields: str | None) -> None:
        self.store.update_user_profile_fields(user_id, **fields)

    def delete(self, user_id: str) -> bool:
        return self.store.delete_user_profile(user_id)


class SqliteUserPromptSettingsRepo(UserPromptSettingsRepo):
    def __init__(self, store: SqliteUserDataStore):
        self.store = store

    def get(self, user_id: str) -> UserPromptSettings | None:
        return self.store.get_prompt_settings(user_id)

    def save(self, settings: UserPromptSettings) -> None:
        self.store.save_prompt_settings(settings)

    def delete(self, user_id: str) -> bool:
        return self.store.delete_prompt_settings(user_id)


class SqliteUserMemoryRepo(UserMemoryRepo):
    def __init__(self, store: SqliteUserDataStore):
        self.store = store

    def get(self, user_id: str) -> str:
        return self.store.get_memory(user_id)

    def set(self, user_id: str, content: str) -> None:
        self.store.set(user_id, content)

    def clear(self, user_id: str) -> None:
        self.store.clear(user_id)


class SqliteMemoRepo(MemoRepo):
    def __init__(self, store: SqliteUserDataStore):
        self.store = store

    def list_items(self, user_id: str) -> list[MemoItem]:
        return self.store.list_items(user_id)

    def save_items(self, user_id: str, items: list[MemoItem]) -> None:
        self.store.save_items(user_id, items)


class SqliteReminderRepo(ReminderRepo):
    def __init__(self, store: SqliteUserDataStore):
        self.store = store

    def list_by_user_and_group(self, user_id: str, group_id: str) -> list[ReminderRecord]:
        return self.store.list_by_user_and_group(user_id, group_id)

    def list_all(self) -> list[ReminderRecord]:
        return self.store.list_all()

    def save(self, record: ReminderRecord) -> None:
        self.store.save_reminder(record)

    def delete_many(self, task_ids: list[str]) -> None:
        self.store.delete_many(task_ids)

    def update_run_time(self, task_id: str, run_time: datetime) -> None:
        self.store.update_run_time(task_id, run_time)
