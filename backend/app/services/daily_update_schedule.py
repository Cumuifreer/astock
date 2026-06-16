from __future__ import annotations

from datetime import time
from typing import List


def parse_daily_update_schedule(value: str) -> List[time]:
    raw_items = [item.strip() for item in str(value or "17:10").split(",")]
    parsed = {_parse_schedule_time(item) for item in raw_items if item}
    return sorted(parsed) or [time(hour=17, minute=10)]


def _parse_schedule_time(value: str) -> time:
    hour, minute = str(value or "17:10").split(":", 1)
    return time(hour=max(0, min(23, int(hour))), minute=max(0, min(59, int(minute))))
