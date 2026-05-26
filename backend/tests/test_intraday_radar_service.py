from datetime import datetime, timedelta

import pandas as pd
import pytest

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


def _bearish_bar(code: str, day: int, close: float = 10.0) -> dict:
    row = _bar(code, day, close)
    row["open"] = row["close"] + 0.08
    row["amount"] = 8_000_000.0 + day * 10_000
    return row


def _dated_bar(code: str, day: int, close: float, high: float, low: float, amount: float = 10_000_000.0) -> dict:
    return {
        "code": code,
        "date": f"2026-04-{day:02d}",
        "open": close - 0.03,
        "high": high,
        "low": low,
        "close": close,
        "prev_close": close - 0.02,
        "volume": 1_000_000.0 + day * 1000,
        "amount": amount + day * 10_000,
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
            "platform_bull_amount_advantage": 0,
            "candidate_limit": 10,
        },
    )
    result = service.latest(limit=10)

    assert count == 1
    assert result["summary"]["candidate_count"] == 1
    row = result["rows"][0]
    assert row["code"] == "000001.SZ"
    assert row["status"] == "刚突破"
    assert row["chart_url"] == "https://finance.sina.com.cn/realstock/company/sz000001/nc.shtml"
    assert row["metrics"]["platform_upper"] == 10.35
    assert row["breakout_clearance"] > 0
    assert "突破上沿" in " / ".join(row["reasons"])


def test_intraday_radar_keeps_strict_and_score_views_for_same_snapshot(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行")], ["code"])
    db.upsert("historical_bars", [_bar("000001.SZ", day) for day in range(1, 22)], ["code", "date"])

    service = IntradayRadarService(db)
    sample_at = datetime(2026, 5, 21, 10, 30)
    service.record_snapshots(
        pd.DataFrame(
            [
                {
                    "code": "000001.SZ",
                    "name": "平安银行",
                    "latest_price": 10.55,
                    "pct_chg": 9.2,
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

    strict_count = service.run_radar(
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

    assert strict_count == 0
    assert result["summary"]["strict_count"] == 0
    assert result["summary"]["score_count"] == 1
    assert result["rows"] == []
    assert result["score_rows"][0]["code"] == "000001.SZ"
    assert result["score_rows"][0]["radar_mode"] == "score"


def test_intraday_radar_strict_requires_platform_bullish_quality(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "弱平台")], ["code"])
    db.upsert("historical_bars", [_bearish_bar("000001.SZ", day) for day in range(1, 22)], ["code", "date"])

    service = IntradayRadarService(db)
    sample_at = datetime(2026, 5, 21, 11, 0)
    service.record_snapshots(
        pd.DataFrame(
            [
                {
                    "code": "000001.SZ",
                    "name": "弱平台",
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

    service.run_radar(
        sample_at=sample_at,
        config={
            "platform_lookback_days": 20,
            "platform_max_range": 0.08,
            "near_upper_distance": 0.03,
            "breakout_min_clearance": 0.0,
            "breakout_max_clearance": 0.08,
            "max_pct_chg": 8.0,
            "min_amount": 20_000_000,
            "platform_min_bullish_ratio": 0.5,
            "platform_bull_amount_advantage": 1.05,
            "candidate_limit": 10,
        },
    )
    result = service.latest(limit=10)

    assert result["summary"]["strict_count"] == 0
    assert result["summary"]["score_count"] == 1
    assert result["score_rows"][0]["metrics"]["platform_bullish_ratio"] == 0.0


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

    service.run_radar(sample_at=second, config={"min_amount": 0, "platform_bull_amount_advantage": 0, "candidate_limit": 10})
    row = service.latest(limit=10)["rows"][0]

    assert row["metrics"]["amount_delta"] == 8_500_000.0
    assert row["metrics"]["volume_delta"] == 800_000.0
    assert row["metrics"]["price_change"] > 0


def test_intraday_timeline_tracks_candidate_across_samples(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行")], ["code"])
    db.upsert("historical_bars", [_bar("000001.SZ", day) for day in range(1, 22)], ["code", "date"])

    service = IntradayRadarService(db)
    first = datetime(2026, 5, 21, 9, 35)
    second = datetime(2026, 5, 21, 10, 0)
    for sample_at, price, amount in [(first, 10.34, 10_000_000.0), (second, 10.55, 32_000_000.0)]:
        service.record_snapshots(
            pd.DataFrame(
                [
                    {
                        "code": "000001.SZ",
                        "name": "平安银行",
                        "latest_price": price,
                        "pct_chg": 3.0,
                        "high": price,
                        "low": 9.9,
                        "volume": amount / 10,
                        "amount": amount,
                        "source": "AkShare 新浪",
                    }
                ]
            ),
            sample_at=sample_at,
            trade_date="2026-05-21",
        )
        service.run_radar(sample_at=sample_at, config={"min_amount": 0, "platform_bull_amount_advantage": 0, "candidate_limit": 10})

    timeline = service.timeline("000001.SZ", trade_date="2026-05-21")

    assert [row["sample_at"] for row in timeline["rows"]] == [first, second]
    assert timeline["code"] == "000001.SZ"
    assert timeline["name"] == "平安银行"
    assert timeline["rows"][0]["strict_status"] == "接近平台"
    assert timeline["rows"][1]["strict_status"] == "刚突破"
    assert timeline["rows"][1]["score_score"] >= timeline["rows"][0]["score_score"]


def test_intraday_radar_queries_previous_snapshots_with_timestamp_param(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行")], ["code"])
    db.upsert("historical_bars", [_bar("000001.SZ", day) for day in range(1, 22)], ["code", "date"])

    service = IntradayRadarService(db)
    first = datetime(2026, 5, 21, 9, 35)
    second = datetime(2026, 5, 21, 14, 30)
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
    original_query = db.query
    previous_snapshot_params = []

    def capture_query(sql, params=None):
        if "sample_at < ?" in sql:
            previous_snapshot_params.append(params[-1])
        return original_query(sql, params)

    monkeypatch.setattr(db, "query", capture_query)
    service.run_radar(sample_at=second, config={"min_amount": 0, "candidate_limit": 10})

    assert previous_snapshot_params
    assert isinstance(previous_snapshot_params[0], datetime)


def test_intraday_radar_normalizes_amount_ratio_by_sample_time(tmp_path):
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
                    "volume": 300_000.0,
                    "amount": 3_000_000.0,
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
            "min_amount": 0,
            "min_intraday_amount_ratio": 1.0,
            "platform_bull_amount_advantage": 0,
            "candidate_limit": 10,
        },
    )
    row = service.latest(limit=10)["rows"][0]

    assert count == 1
    assert row["amount_ratio"] == pytest.approx(1.48, abs=0.02)
    assert row["metrics"]["intraday_time_progress"] == pytest.approx(0.2)


def test_intraday_radar_strict_rejects_candidates_that_already_broke_platform(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "前高已破")], ["code"])
    base_platform = [
        _dated_bar("000001.SZ", day, close=10.0 + (0.01 if day % 2 else -0.01), high=10.35, low=9.75)
        for day in range(1, 21)
    ]
    prior_breakout = [
        _dated_bar("000001.SZ", day, close=10.72, high=10.82, low=10.35, amount=18_000_000.0)
        for day in range(21, 26)
    ]
    db.upsert("historical_bars", base_platform + prior_breakout, ["code", "date"])

    service = IntradayRadarService(db)
    sample_at = datetime(2026, 5, 21, 10, 30)
    service.record_snapshots(
        pd.DataFrame(
            [
                {
                    "code": "000001.SZ",
                    "name": "前高已破",
                    "latest_price": 10.9,
                    "pct_chg": 4.0,
                    "high": 10.95,
                    "low": 10.3,
                    "volume": 3_100_000.0,
                    "amount": 62_000_000.0,
                    "source": "AkShare 新浪",
                }
            ]
        ),
        sample_at=sample_at,
        trade_date="2026-05-21",
    )

    service.run_radar(
        sample_at=sample_at,
        config={
            "platform_lookback_days": 20,
            "platform_max_range": 0.12,
            "first_breakout_lookback_days": 5,
            "first_breakout_max_clearance": 0.02,
            "near_upper_recent_days": 3,
            "near_upper_recent_distance": 0.03,
            "min_amount": 0,
            "min_intraday_amount_ratio": 0,
            "candidate_limit": 10,
        },
    )
    result = service.latest(limit=10)

    assert result["summary"]["strict_count"] == 0
    assert result["summary"]["score_count"] == 1
    assert result["score_rows"][0]["metrics"]["recent_prior_breakout_clearance"] > 0.02


def test_intraday_radar_strict_requires_recent_prices_near_platform_upper(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "远离平台")], ["code"])
    bars = [_bar("000001.SZ", day) for day in range(1, 19)]
    bars.extend(
        [
            _dated_bar("000001.SZ", 19, close=9.80, high=9.88, low=9.72),
            _dated_bar("000001.SZ", 20, close=9.82, high=9.90, low=9.74),
            _dated_bar("000001.SZ", 21, close=9.84, high=9.92, low=9.76),
        ]
    )
    db.upsert("historical_bars", bars, ["code", "date"])

    service = IntradayRadarService(db)
    sample_at = datetime(2026, 5, 21, 10, 30)
    service.record_snapshots(
        pd.DataFrame(
            [
                {
                    "code": "000001.SZ",
                    "name": "远离平台",
                    "latest_price": 10.20,
                    "pct_chg": 2.0,
                    "high": 10.25,
                    "low": 9.8,
                    "volume": 3_100_000.0,
                    "amount": 62_000_000.0,
                    "source": "AkShare 新浪",
                }
            ]
        ),
        sample_at=sample_at,
        trade_date="2026-05-21",
    )

    service.run_radar(
        sample_at=sample_at,
        config={
            "platform_lookback_days": 20,
            "platform_max_range": 0.12,
            "near_upper_distance": 0.03,
            "near_upper_recent_days": 3,
            "near_upper_recent_distance": 0.03,
            "first_breakout_lookback_days": 0,
            "min_amount": 0,
            "min_intraday_amount_ratio": 0,
            "candidate_limit": 10,
        },
    )
    result = service.latest(limit=10)

    assert result["summary"]["strict_count"] == 0
    assert result["summary"]["score_count"] == 1
    assert result["score_rows"][0]["metrics"]["recent_near_upper_distance"] > 0.03


def test_intraday_radar_strict_applies_intraday_pct_change_floor(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "涨幅不足")], ["code"])
    db.upsert("historical_bars", [_bar("000001.SZ", day) for day in range(1, 22)], ["code", "date"])

    service = IntradayRadarService(db)
    sample_at = datetime(2026, 5, 21, 10, 0)
    service.record_snapshots(
        pd.DataFrame(
            [
                {
                    "code": "000001.SZ",
                    "name": "涨幅不足",
                    "latest_price": 10.55,
                    "pct_chg": -0.4,
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

    service.run_radar(
        sample_at=sample_at,
        config={
            "platform_lookback_days": 20,
            "platform_max_range": 0.08,
            "min_pct_chg": 0.0,
            "max_pct_chg": 6.0,
            "min_amount": 0,
            "min_intraday_amount_ratio": 0,
            "candidate_limit": 10,
        },
    )
    result = service.latest(limit=10)

    assert result["summary"]["strict_count"] == 0
    assert result["summary"]["score_count"] == 1


def test_intraday_task_records_snapshot_and_runs_radar(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行")], ["code"])
    db.upsert("historical_bars", [_bar("000001.SZ", day) for day in range(1, 22)], ["code", "date"])
    IntradayRadarService(db).save_config(
        {
            "min_amount": 0,
            "platform_bull_amount_advantage": 0,
            "candidate_limit": 10,
        }
    )

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


def test_intraday_snapshot_prefers_tushare_realtime(tmp_path, monkeypatch):
    from types import SimpleNamespace

    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class FakeTushareSource:
        def fetch_realtime_daily(self, include_bj=False, exclude_star=False):
            return pd.DataFrame(
                [
                    {
                        "code": "000001.SZ",
                        "date": "2026-05-21",
                        "name": "平安银行",
                        "latest_price": 10.55,
                        "pct_chg": 4.2,
                        "high": 10.6,
                        "low": 9.9,
                        "volume": 3_100_000.0,
                        "amount": 62_000_000.0,
                        "source": "Tushare 实时日线",
                    }
                ]
            )

    monkeypatch.setattr("backend.app.services.update_service.TushareRealtimeSource", FakeTushareSource)
    monkeypatch.setattr(
        "backend.app.services.update_service.settings",
        SimpleNamespace(
            tushare_realtime_enabled=True,
            tushare_token="test-token",
            tushare_timeout_seconds=5,
            source_probe_ttl_minutes=60,
        ),
    )
    monkeypatch.setattr(
        "backend.app.services.update_service.AkShareSource.fetch_sina_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("AkShare should not be called")),
    )

    frame = service._fetch_intraday_snapshot_frame(include_bj=False, exclude_star=False, warnings=[])

    assert frame.iloc[0]["source"] == "Tushare 实时日线"
