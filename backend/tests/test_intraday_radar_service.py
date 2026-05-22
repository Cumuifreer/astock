from datetime import datetime, timedelta

import pandas as pd

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.intraday_service import IntradayRadarService
from backend.app.services.update_service import UpdateService


def _stock(code: str, name: str) -> dict:
    return {
        "code": code,
        "name": name,
        "exchange": code.split(".")[-1],
        "list_date": "2020-01-01",
        "source": "test",
        "is_st": False,
        "suspended": False,
        "updated_at": "2026-05-21T09:00:00",
    }


def _bar(code: str, day: int, close: float = 10.0) -> dict:
    price = close + (0.02 if day % 2 else -0.02)
    open_price = price - (0.05 if day % 3 else -0.03)
    return {
        "code": code,
        "date": f"2026-04-{day:02d}",
        "open": open_price,
        "high": 10.35,
        "low": 9.75,
        "close": price,
        "prev_close": close,
        "volume": 1_000_000.0 + day * 1000,
        "amount": 10_000_000.0 + day * 10_000,
        "turn": 2.0,
        "pct_chg": 0.2,
        "tradestatus": "1",
        "is_st": False,
        "source": "Baostock",
        "updated_at": "2026-05-21T09:00:00",
    }


def test_intraday_radar_scores_latest_snapshot_against_platform(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行")], ["code"])
    db.upsert("historical_bars", [_bar("000001.SZ", day) for day in range(1, 22)], ["code", "date"])

    service = IntradayRadarService(db)
    sample_at = datetime(2026, 5, 21, 10, 0)
    service.record_snapshots(
        pd.DataFrame(
            [
                {
                    "code": "000001.SZ",
                    "name": "平安银行",
                    "latest_price": 10.55,
                    "pct_chg": 4.2,
                    "high": 10.6,
                    "low": 9.9,
                    "volume": 3_100_000.0,
                        "amount": 62_000_000.0,
                    "source": "AkShare 新浪",
                }
            ]
        ),
        sample_at=sample_at,
        trade_date="2026-05-21",
    )

    count = service.run_radar(
        sample_at=sample_at,
        config={
            "platform_lookback_days": 20,
            "platform_max_range": 0.08,
            "near_upper_distance": 0.03,
            "breakout_min_clearance": 0.0,
            "breakout_max_clearance": 0.08,
            "max_pct_chg": 8.0,
            "min_amount": 20_000_000,
            "candidate_limit": 10,
        },
    )
    result = service.latest(limit=10)

    assert count == 1
    assert result["summary"]["candidate_count"] == 1
    row = result["rows"][0]
    assert row["code"] == "000001.SZ"
    assert row["status"] == "刚突破"
    assert row["metrics"]["platform_upper"] == 10.35
    assert row["breakout_clearance"] > 0
    assert "突破上沿" in " / ".join(row["reasons"])


def test_intraday_radar_uses_previous_snapshot_deltas(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行")], ["code"])
    db.upsert("historical_bars", [_bar("000001.SZ", day) for day in range(1, 22)], ["code", "date"])

    service = IntradayRadarService(db)
    first = datetime(2026, 5, 21, 9, 35)
    second = first + timedelta(minutes=25)
    common = {
        "code": "000001.SZ",
        "name": "平安银行",
        "pct_chg": 3.5,
        "high": 10.45,
        "low": 9.9,
        "source": "AkShare 新浪",
    }
    service.record_snapshots(
        pd.DataFrame([{**common, "latest_price": 10.35, "volume": 1_000_000.0, "amount": 10_000_000.0}]),
        sample_at=first,
        trade_date="2026-05-21",
    )
    service.record_snapshots(
        pd.DataFrame([{**common, "latest_price": 10.55, "volume": 1_800_000.0, "amount": 18_500_000.0}]),
        sample_at=second,
        trade_date="2026-05-21",
    )

    service.run_radar(sample_at=second, config={"min_amount": 0, "candidate_limit": 10})
    row = service.latest(limit=10)["rows"][0]

    assert row["metrics"]["amount_delta"] == 8_500_000.0
    assert row["metrics"]["volume_delta"] == 800_000.0
    assert row["metrics"]["price_change"] > 0


def test_intraday_task_records_snapshot_and_runs_radar(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行")], ["code"])
    db.upsert("historical_bars", [_bar("000001.SZ", day) for day in range(1, 22)], ["code", "date"])

    service = UpdateService(db)

    class ImmediateExecutor:
        def submit(self, fn, *args):
            fn(*args)

    monkeypatch.setattr(service, "executor", ImmediateExecutor())
    monkeypatch.setattr(
        service,
        "_fetch_intraday_snapshot_frame",
        lambda include_bj, exclude_star, warnings: pd.DataFrame(
            [
                {
                    "code": "000001.SZ",
                    "name": "平安银行",
                    "latest_price": 10.55,
                    "pct_chg": 4.2,
                    "high": 10.6,
                    "low": 9.9,
                    "volume": 3_100_000.0,
                    "amount": 62_000_000.0,
                    "source": "AkShare 新浪",
                }
            ]
        ),
    )

    task_id = service.start_intraday_sample({"sample_at": "2026-05-21T10:00:00"})
    task = db.query("SELECT * FROM task_runs WHERE id = ?", [task_id])[0]
    radar = IntradayRadarService(db).latest()

    assert task["status"] == "completed_full"
    assert task["kind"] == "intraday"
    assert radar["summary"]["candidate_count"] == 1
    assert radar["rows"][0]["status"] == "刚突破"
