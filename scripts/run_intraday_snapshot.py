from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo


CHINA_TZ = ZoneInfo("Asia/Shanghai")


def main() -> int:
    now = datetime.now(CHINA_TZ)
    if os.getenv("ASHARE_INTRADAY_FORCE", "0") != "1":
        if now.weekday() >= 5:
            print(f"skip weekend: {now:%Y-%m-%d %H:%M}")
            return 0
        schedule = _schedule()
        current = now.strftime("%H:%M")
        if current not in schedule:
            print(f"skip outside schedule: {current}")
            return 0

    base_url = os.getenv("ASHARE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    payload = json.dumps({}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/tasks/intraday-snapshot",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            print(response.read().decode("utf-8"))
            return 0
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"request failed: {exc.code} {body}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"request failed: {exc}", file=sys.stderr)
        return 1


def _schedule() -> set[str]:
    raw = os.getenv(
        "ASHARE_INTRADAY_SCHEDULE",
        "09:35,10:00,10:30,11:00,11:25,13:00,13:30,14:00,14:30,14:55",
    )
    return {item.strip() for item in raw.split(",") if item.strip()}


if __name__ == "__main__":
    raise SystemExit(main())
