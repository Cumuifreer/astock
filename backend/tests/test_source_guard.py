from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.sources.base import SourceGuard
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


def test_sina_global_interval_skips_second_full_market_request(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    service.public_guard.record("AkShare 新浪", "当天行情快照", "available", payload={"rows": 5000})

    def unexpected_request(*_args, **_kwargs):
        raise AssertionError("interval gate must run before AkShare")

    monkeypatch.setattr(
        "backend.app.services.update_service.AkShareSource.fetch_sina_snapshot",
        unexpected_request,
    )

    result = service._fetch_sina_snapshot("盘中行情快照", include_bj=False, exclude_star=False)

    assert result.status == "skipped"
    assert "过近" in str(result.message)
