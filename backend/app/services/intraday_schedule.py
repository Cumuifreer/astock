from __future__ import annotations

import logging
from typing import List, Sequence, Tuple

IntradaySlot = Tuple[int, int]

DEFAULT_INTRADAY_SLOTS: Tuple[IntradaySlot, ...] = (
    (9, 35),
    (9, 45),
    (9, 55),
    (10, 5),
    (10, 15),
    (10, 25),
    (10, 35),
    (10, 45),
    (10, 55),
    (11, 5),
    (11, 15),
    (11, 25),
    (13, 0),
    (13, 10),
    (13, 20),
    (13, 30),
    (13, 40),
    (13, 50),
    (14, 0),
    (14, 10),
    (14, 20),
    (14, 30),
    (14, 40),
    (14, 50),
    (14, 55),
)
DEFAULT_INTRADAY_SCHEDULE_TEXT = ",".join(
    f"{hour:02d}:{minute:02d}" for hour, minute in DEFAULT_INTRADAY_SLOTS
)
LIGHT_INTRADAY_SLOTS: Tuple[IntradaySlot, ...] = (
    (9, 35),
    (10, 35),
    (11, 25),
    (13, 30),
    (14, 30),
    (14, 55),
)
LIGHT_INTRADAY_SCHEDULE_TEXT = ",".join(
    f"{hour:02d}:{minute:02d}" for hour, minute in LIGHT_INTRADAY_SLOTS
)


def parse_intraday_schedule(raw: str | None) -> List[IntradaySlot]:
    text = (raw or "").strip()
    if not text:
        return list(DEFAULT_INTRADAY_SLOTS)
    slots: set[IntradaySlot] = set()
    invalid: list[str] = []
    for item in text.split(","):
        token = item.strip()
        if not token:
            continue
        try:
            hour_text, minute_text = token.split(":", 1)
            hour = int(hour_text)
            minute = int(minute_text)
        except ValueError:
            invalid.append(token)
            continue
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            invalid.append(token)
            continue
        slots.add((hour, minute))
    if invalid:
        logging.warning("忽略无效盘中采样时间: %s", ",".join(invalid))
    return sorted(slots) if slots else list(DEFAULT_INTRADAY_SLOTS)


def format_intraday_schedule(slots: Sequence[IntradaySlot]) -> List[str]:
    return [f"{hour:02d}:{minute:02d}" for hour, minute in slots]
