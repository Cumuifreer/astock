from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

import pandas as pd

from backend.app.db import Database


class SourceUnavailable(RuntimeError):
    pass


@dataclass
class SourceFetchResult:
    source: str
    capability: str
    frame: pd.DataFrame = field(default_factory=pd.DataFrame)
    status: str = "available"
    message: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)


class SourceGuard:
    def __init__(self, db: Database, min_delay: float, max_delay: float):
        self.db = db
        self.min_delay = min_delay
        self.max_delay = max_delay

    def sleep(self, attempt: int = 0) -> None:
        base = random.uniform(self.min_delay, self.max_delay)
        time.sleep(base + min(8.0, attempt * attempt * 0.4))

    def record(
        self,
        source: str,
        capability: str,
        status: str,
        message: Optional[str] = None,
        ttl_minutes: int = 60,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        now = datetime.utcnow()
        row = {
            "source": source,
            "capability": capability,
            "status": status,
            "last_checked": now,
            "last_success": now if status in {"available", "completed_full", "completed_partial"} else None,
            "last_failure": now if status in {"unavailable", "failed"} else None,
            "failure_reason": message if status in {"unavailable", "failed"} else None,
            "ttl_until": now + timedelta(minutes=ttl_minutes),
            "payload_json": payload or {},
        }
        self.db.upsert("source_status", [row], ["source", "capability"])

    def is_circuit_open(self, source: str, capability: str) -> bool:
        rows = self.db.query(
            """
            SELECT status, ttl_until
            FROM source_status
            WHERE source = ? AND capability = ?
            """,
            [source, capability],
        )
        if not rows:
            return False
        row = rows[0]
        ttl = row.get("ttl_until")
        if row.get("status") not in {"unavailable", "failed"} or ttl is None:
            return False
        if isinstance(ttl, str):
            ttl_value = datetime.fromisoformat(ttl)
        else:
            ttl_value = ttl
        return ttl_value > datetime.utcnow()

    def call(
        self,
        source: str,
        capability: str,
        fetcher: Callable[[], pd.DataFrame],
        ttl_minutes: int = 60,
        max_attempts: int = 2,
        ignore_circuit: bool = False,
        timeout_seconds: int = 60,
    ) -> SourceFetchResult:
        if not ignore_circuit and self.is_circuit_open(source, capability):
            return SourceFetchResult(
                source=source,
                capability=capability,
                status="skipped",
                message="数据源熔断保护中，继续使用本地缓存。",
            )
        last_error: Optional[Exception] = None
        for attempt in range(max_attempts):
            if attempt:
                self.sleep(attempt)
            try:
                frame = self._call_with_timeout(fetcher, timeout_seconds)
                if frame is None or frame.empty:
                    raise SourceUnavailable("接口返回空数据。")
                self.record(
                    source,
                    capability,
                    "available",
                    ttl_minutes=ttl_minutes,
                    payload={"rows": len(frame)},
                )
                return SourceFetchResult(source=source, capability=capability, frame=frame)
            except Exception as exc:
                last_error = exc
        message = str(last_error) if last_error else "未知错误"
        self.record(source, capability, "failed", message=message, ttl_minutes=ttl_minutes)
        return SourceFetchResult(
            source=source,
            capability=capability,
            status="failed",
            message=message,
        )

    @staticmethod
    def _call_with_timeout(fetcher: Callable[[], pd.DataFrame], timeout_seconds: int) -> pd.DataFrame:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(fetcher)
        try:
            return future.result(timeout=timeout_seconds)
        except TimeoutError:
            future.cancel()
            raise SourceUnavailable(f"接口超过 {timeout_seconds} 秒未返回。")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)


def first_present(row: Dict[str, Any], candidates: list) -> Any:
    for key in candidates:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None
