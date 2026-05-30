from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from croniter import croniter

_WEEKDAY_TO_CRON = {
    0: 'mon',  # Monday
    1: 'tue',  # Tuesday
    2: 'wed',  # Wednesday
    3: 'thu',  # Thursday
    4: 'fri',  # Friday
    5: 'sat',  # Saturday
    6: 'sun',  # Sunday
}


@dataclass(slots=True, frozen=True)
class ScheduleRule:
    hour: int
    minute: int
    weekly_days: tuple[int, ...] = field(default_factory=tuple)
    month_days: tuple[int, ...] = field(default_factory=tuple)
    union_weekly_monthly: bool = False

    def __post_init__(self) -> None:
        if not 0 <= self.hour <= 23:
            raise ValueError("hour 必须在 0..23")
        if not 0 <= self.minute <= 59:
            raise ValueError("minute 必须在 0..59")
        if any(day < 0 or day > 6 for day in self.weekly_days):
            raise ValueError("weekly_days 必须在 0..6，周一=0，周日=6")
        if any(day < 1 or day > 31 for day in self.month_days):
            raise ValueError("month_days 必须在 1..31")

    def to_cron(self) -> tuple[str, bool]:
        minute = str(self.minute)
        hour = str(self.hour)

        has_weekly = bool(self.weekly_days)
        has_monthly = bool(self.month_days)

        if has_weekly:
            cron_weekdays = ",".join(_WEEKDAY_TO_CRON[d] for d in sorted(set(self.weekly_days)))
        else:
            cron_weekdays = "*"

        if has_monthly:
            cron_month_days = ",".join(str(d) for d in sorted(set(self.month_days)))
        else:
            cron_month_days = "*"

        if has_weekly and has_monthly and not self.union_weekly_monthly:
            # 周优先，丢弃按月规则。
            cron_month_days = "*"

        cron = f"{minute} {hour} {cron_month_days} * {cron_weekdays}"
        day_or = bool(has_weekly and has_monthly and self.union_weekly_monthly)
        return cron, day_or

    def next_run_after(self, after: datetime) -> datetime:
        cron, day_or = self.to_cron()
        return croniter(cron, after, day_or=day_or).get_next(datetime)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hour": self.hour,
            "minute": self.minute,
            "weekly_days": list(self.weekly_days),
            "month_days": list(self.month_days),
            "union_weekly_monthly": self.union_weekly_monthly,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ScheduleRule | None":
        if not data:
            return None
        return cls(
            hour=int(data["hour"]),
            minute=int(data["minute"]),
            weekly_days=tuple(int(x) for x in data.get("weekly_days", [])),
            month_days=tuple(int(x) for x in data.get("month_days", data.get("monthly_days", []))),
            union_weekly_monthly=bool(data.get("union_weekly_monthly", False)),
        )

    def display_text(self) -> str:
        parts: list[str] = []
        parts.append(f"{self.hour:02d}:{self.minute:02d}")

        if self.weekly_days:
            names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            parts.append("每周" + "、".join(names[d] for d in sorted(set(self.weekly_days))))

        if self.month_days:
            month_text = "每月" + "、".join(str(d) for d in sorted(set(self.month_days))) + "日"
            if self.weekly_days and not self.union_weekly_monthly:
                month_text += "（已被周规则覆盖）"
            parts.append(month_text)

        if not self.weekly_days and not self.month_days:
            parts.append("每日")

        if self.weekly_days and self.month_days and self.union_weekly_monthly:
            parts.append("周/月并集")

        return " ".join(parts)
