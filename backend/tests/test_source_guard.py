import time

import pandas as pd
import pytest

from backend.app.db import Database
from backend.app.config import settings
from backend.app.schema import migrate
from backend.app.sources.base import SourceFetchResult, SourceGuard, SourceUnavailable
from backend.app.services.update_service import UpdateService


def test_source_guard_preserves_last_success_across_later_failures(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    guard = SourceGuard(db, min_delay=0, max_delay=0)

    guard.record("AkShare 新浪", "盘中行情快照", "available", payload={"rows": 5000})
    first_success = db.scalar(
        "SELECT last_success FROM source_status WHERE source = ? AND capability = ?",
        ["AkShare 新浪", "盘中行情快照"],
    )
    guard.record("AkShare 新浪", "盘中行情快照", "failed", message="temporary failure")
    row = db.query(
        "SELECT last_success, last_failure, failure_reason FROM source_status WHERE source = ? AND capability = ?",
        ["AkShare 新浪", "盘中行情快照"],
    )[0]

    assert row["last_success"] == first_success
    assert row["last_failure"] is not None
    assert row["failure_reason"] == "temporary failure"






def test_source_guard_outer_timeout_returns_control_for_hung_fetcher():
    def hung_fetcher():
        time.sleep(0.2)
        return pd.DataFrame([{"code": "000001.SZ"}])

    with pytest.raises(SourceUnavailable, match="接口超过"):
        SourceGuard._call_with_timeout(hung_fetcher, timeout_seconds=0.01)
