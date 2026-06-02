from __future__ import annotations

import logging
import threading
from datetime import datetime, time
from typing import List, Optional
from zoneinfo import ZoneInfo

from backend.app.services.update_service import UpdateService


CHINA_TZ = ZoneInfo("Asia/Shanghai")


class DailyBriefScheduler:
    def __init__(
        self,
        update_service: UpdateService,
        poll_seconds: int = 60,
        schedule_time: str = "08:20",
    ):
        self.update_service = update_service
        self.poll_seconds = max(10, int(poll_seconds))
        self.schedule_times = _parse_schedule_times(schedule_time)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="daily-brief-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def tick(self, now: Optional[datetime] = None) -> Optional[str]:
        return None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                logging.exception("每日资讯简报自动任务检查失败")
            self._stop.wait(self.poll_seconds)


def _parse_schedule_times(value: str) -> List[time]:
    raw_items = [item.strip() for item in str(value or "08:20").split(",")]
    parsed = {_parse_schedule_time(item) for item in raw_items if item}
    return sorted(parsed) or [time(hour=8, minute=20)]


def _parse_schedule_time(value: str) -> time:
    hour, minute = str(value or "08:20").split(":", 1)
    return time(hour=max(0, min(23, int(hour))), minute=max(0, min(59, int(minute))))
