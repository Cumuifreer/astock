from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from backend.app.services.update_service import UpdateService

CHINA_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_INTRADAY_SLOTS: Tuple[Tuple[int, int], ...] = (
    (9, 35),
    (10, 0),
    (10, 30),
    (11, 0),
    (11, 25),
    (13, 0),
    (13, 30),
    (14, 0),
    (14, 30),
    (14, 55),
)


class IntradayScheduler:
    def __init__(
        self,
        update_service: UpdateService,
        poll_seconds: int = 30,
        catchup_minutes: int = 8,
        slots: Sequence[Tuple[int, int]] = DEFAULT_INTRADAY_SLOTS,
    ):
        self.update_service = update_service
        self.poll_seconds = max(5, int(poll_seconds))
        self.catchup_minutes = max(1, int(catchup_minutes))
        self.slots = tuple(slots)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="intraday-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def tick(self, now: Optional[datetime] = None) -> Optional[str]:
        slot = self._due_slot(now or datetime.now(CHINA_TZ))
        if slot is None:
            return None
        return self.update_service.start_scheduled_intraday_sample(slot)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                logging.exception("盘中雷达自动采样检查失败")
            self._stop.wait(self.poll_seconds)

    def _due_slot(self, now: datetime) -> Optional[datetime]:
        current = now.astimezone(CHINA_TZ) if now.tzinfo else now.replace(tzinfo=CHINA_TZ)
        if current.weekday() >= 5:
            return None
        window = timedelta(minutes=self.catchup_minutes)
        for hour, minute in self.slots:
            slot = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if slot <= current < slot + window:
                return slot.replace(tzinfo=None)
        return None
