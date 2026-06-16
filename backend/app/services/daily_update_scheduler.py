from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from backend.app.services.daily_update_schedule import parse_daily_update_schedule
from backend.app.services.update_service import UpdateService


CHINA_TZ = ZoneInfo("Asia/Shanghai")


class DailyUpdateScheduler:
    def __init__(
        self,
        update_service: UpdateService,
        poll_seconds: int = 60,
        schedule_time: str = "17:10",
        mode: str = "daily_light",
    ):
        self.update_service = update_service
        self.poll_seconds = max(10, int(poll_seconds))
        self.schedule_times = parse_daily_update_schedule(schedule_time)
        self.mode = mode or "daily_light"
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="daily-update-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def tick(self, now: Optional[datetime] = None) -> Optional[str]:
        current = now or datetime.now(CHINA_TZ)
        current = current.astimezone(CHINA_TZ) if current.tzinfo else current.replace(tzinfo=CHINA_TZ)
        if current.weekday() >= 5:
            return None
        due_slots = [
            current.replace(hour=item.hour, minute=item.minute, second=0, microsecond=0)
            for item in self.schedule_times
            if current >= current.replace(hour=item.hour, minute=item.minute, second=0, microsecond=0)
        ]
        if not due_slots:
            return None
        slot = due_slots[-1]
        return self.update_service.start_scheduled_daily_update(slot.replace(tzinfo=None), mode=self.mode)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                logging.exception("每日数据更新自动任务检查失败")
            self._stop.wait(self.poll_seconds)
