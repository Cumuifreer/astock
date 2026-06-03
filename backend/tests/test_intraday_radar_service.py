import json
from datetime import datetime, timedelta

import pandas as pd
import pytest

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.intraday_service import IntradayRadarService
from backend.app.services.strategy_service import StrategyService
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


def test_intraday_latest_uses_latest_snapshot_even_when_no_candidates(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行")], ["code"])
    db.upsert("historical_bars", [_bar("000001.SZ", day) for day in range(1, 22)], ["code", "date"])

    service = IntradayRadarService(db)
    first = datetime(2026, 5, 21, 10, 0)
    second = datetime(2026, 5, 21, 10, 30)
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
                    "source": "Tushare 实时日线",
                }
            ]
        ),
        sample_at=first,
        trade_date="2026-05-21",
    )
    service.run_radar(sample_at=first, config={"min_amount": 0, "platform_bull_amount_advantage": 0})
    service.record_snapshots(
        pd.DataFrame(
            [
                {
                    "code": "000001.SZ",
                    "name": "平安银行",
                    "latest_price": 8.8,
                    "pct_chg": -3.0,
                    "high": 9.0,
                    "low": 8.6,
                    "volume": 500_000.0,
                    "amount": 5_000_000.0,
                    "source": "Tushare 实时日线",
                }
            ]
        ),
        sample_at=second,
        trade_date="2026-05-21",
    )
    service.run_radar(sample_at=second, config={"min_amount": 0, "platform_bull_amount_advantage": 0})

    result = service.latest(limit=10)

    assert result["sample_at"] == second
    assert result["sample_count"] == 1
    assert result["rows"] == []
    assert result["strict_rows"] == []
    assert result["score_rows"] == []
    assert result["summary"]["strict_count"] == 0
    assert result["summary"]["score_count"] == 0
    assert result["summary"]["zero_reason"]


def test_intraday_get_config_returns_default_without_persisting(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = IntradayRadarService(db)

    config = service.get_config()

    assert config["enabled"] is True
    assert config["enabled_boards"] == {"anomaly": False, "pullback": False, "risk": False}
    assert db.scalar("SELECT COUNT(*) FROM intraday_radar_config") == 0


def test_intraday_config_normalizes_board_switches(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = IntradayRadarService(db)

    config = service.save_config(
        {
            "enabled_boards": {
                "anomaly": True,
                "pullback": False,
                "risk": True,
                "unknown": True,
            }
        }
    )

    assert config["enabled_boards"] == {"anomaly": True, "pullback": False, "risk": True}
    assert service.get_config()["enabled_boards"] == config["enabled_boards"]


def test_intraday_record_snapshots_filters_untrusted_rows_before_insert(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = IntradayRadarService(db)
    sample_at = datetime(2026, 5, 21, 10, 0)

    written = service.record_snapshots(
        pd.DataFrame(
            [
                {
                    "code": "000001.SZ",
                    "name": "平安银行",
                    "latest_price": 10.5,
                    "pct_chg": 4.0,
                    "high": 10.6,
                    "low": 9.9,
                    "volume": 1_000_000.0,
                    "amount": 12_000_000.0,
                    "tradestatus": "1",
                    "source": "Tushare 实时日线",
                    "freshness": "realtime",
                },
                { "code": "000002.SZ", "name": "负价格", "latest_price": -1, "high": 10.0, "low": 9.0, "amount": 1_000_000.0 },
                { "code": "000003.SZ", "name": "高低错", "latest_price": 10.0, "high": 9.0, "low": 10.0, "amount": 1_000_000.0 },
                { "code": "000004.SZ", "name": "涨幅错", "latest_price": 10.0, "pct_chg": 88.0, "high": 10.0, "low": 9.0, "amount": 1_000_000.0 },
                { "code": "000005.SZ", "name": "负金额", "latest_price": 10.0, "high": 10.0, "low": 9.0, "amount": -1.0 },
                { "code": "000006.SZ", "name": "ST测试", "latest_price": 10.0, "high": 10.0, "low": 9.0, "amount": 1_000_000.0 },
                { "code": "000007.SZ", "name": "停牌", "latest_price": 10.0, "high": 10.0, "low": 9.0, "amount": 1_000_000.0, "tradestatus": "0" },
                { "code": "000008.SZ", "name": "源停牌", "latest_price": 10.0, "high": 10.0, "low": 9.0, "amount": 1_000_000.0, "source": "停牌快照" },
                { "code": "000009.SZ", "name": "日线回退", "latest_price": 10.0, "high": 10.0, "low": 9.0, "amount": 1_000_000.0, "source": "Tushare 日线回退", "freshness": "daily_fallback" },
            ]
        ),
        sample_at=sample_at,
        trade_date="2026-05-21",
    )

    rows = db.query("SELECT code FROM intraday_snapshots ORDER BY code")

    assert written == 1
    assert rows == [{"code": "000001.SZ"}]


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
    service.save_config({"enabled_boards": {"anomaly": True}})
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


def test_intraday_boards_flatten_metrics_and_compute_theme_sync(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行")], ["code"])
    db.upsert("historical_bars", [_bar("000001.SZ", day, close=10.0) for day in range(1, 22)], ["code", "date"])
    db.upsert(
        "tushare_ths_member",
        [
            {
                "code": "000001.SZ",
                "name": "平安银行",
                "con_code": "885800.TI",
                "con_name": "超级电容",
                "weight": None,
                "in_date": "2020-01-01",
                "out_date": None,
                "is_new": "Y",
                "source": "test",
                "updated_at": "2026-05-21T09:00:00",
            }
        ],
        ["code", "con_code"],
    )
    db.upsert(
        "market_sector_daily",
        [
            {
                "sector_code": "885800.TI",
                "sector_name": "超级电容",
                "sector_type": "concept",
                "trade_date": "2026-05-21",
                "pct_chg": 2.1,
                "amount": 1_000_000_000.0,
                "net_amount": 120_000_000.0,
                "company_count": 20,
                "limit_up_count": 2,
                "strong_count": 6,
                "leader_code": "000001.SZ",
                "leader_name": "平安银行",
                "heat_score": 72.0,
                "source": "test",
                "updated_at": "2026-05-21T10:00:00",
            }
        ],
        ["sector_code", "sector_type", "trade_date"],
    )

    service = IntradayRadarService(db)
    service.save_config({"enabled_boards": {"anomaly": True}})
    first = datetime(2026, 5, 21, 9, 35)
    second = datetime(2026, 5, 21, 10, 0)
    base_snapshot = {
        "code": "000001.SZ",
        "name": "平安银行",
        "latest_price": 10.4,
        "pct_chg": 4.0,
        "high": 10.45,
        "low": 9.9,
        "volume": 1_000_000.0,
        "amount": 10_000_000.0,
        "source": "test",
    }
    service.record_snapshots(pd.DataFrame([base_snapshot]), sample_at=first, trade_date="2026-05-21")
    service.record_snapshots(
        pd.DataFrame([{**base_snapshot, "latest_price": 10.5, "high": 10.55, "amount": 60_000_000.0}]),
        sample_at=second,
        trade_date="2026-05-21",
    )

    boards = service.boards(sample_at=second, limit=10)
    row = boards["anomaly"][0]

    assert row["intraday_amount_speed"] is not None
    assert row["amount_delta"] == 50_000_000.0
    assert row["theme_sync_score"] == 0.72
    assert row["strong_theme_name"] == "超级电容"
    assert row["metrics"]["theme_sync_score"] == 0.72


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
    assert timeline["rows"][1]["amount_delta"] == 22_000_000.0
    assert timeline["rows"][1]["amount_delta_status"] == "computed"


def test_intraday_timeline_computes_amount_delta_without_rankings(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行")], ["code"])
    db.upsert("historical_bars", [{**_bar("000001.SZ", day), "amount": 20_000_000.0} for day in range(1, 22)], ["code", "date"])

    service = IntradayRadarService(db)
    first = datetime(2026, 5, 21, 9, 35)
    second = datetime(2026, 5, 21, 10, 0)
    for sample_at, amount in [(first, 10_000_000.0), (second, 32_000_000.0)]:
        service.record_snapshots(
            pd.DataFrame(
                [
                    {
                        "code": "000001.SZ",
                        "name": "平安银行",
                        "latest_price": 10.0,
                        "pct_chg": 1.0,
                        "high": 10.2,
                        "low": 9.8,
                        "volume": amount / 10,
                        "amount": amount,
                        "source": "test",
                    }
                ]
            ),
            sample_at=sample_at,
            trade_date="2026-05-21",
        )

    timeline = service.timeline("000001.SZ", trade_date="2026-05-21")

    assert timeline["rows"][0]["amount_delta"] is None
    assert timeline["rows"][0]["amount_delta_status"] == "insufficient_samples"
    assert timeline["rows"][1]["amount_delta"] == 22_000_000.0
    assert timeline["rows"][1]["amount_delta_status"] == "computed"
    assert timeline["rows"][1]["amount_ratio"] is not None


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
        if "sample_at < CAST(? AS TIMESTAMP)" in sql:
            previous_snapshot_params.append(params[-1])
        return original_query(sql, params)

    monkeypatch.setattr(db, "query", capture_query)
    service.run_radar(sample_at=second, config={"min_amount": 0, "candidate_limit": 10})

    assert previous_snapshot_params
    assert previous_snapshot_params[0] == "2026-05-21T14:30:00"


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


def test_intraday_strategy_tracking_persists_preset_id_and_uses_latest_config(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行")], ["code"])
    db.upsert("historical_bars", [_bar("000001.SZ", day) for day in range(1, 22)], ["code", "date"])
    sample_at = datetime(2026, 5, 21, 10, 0)
    db.upsert(
        "daily_snapshots",
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
                "turnover_rate": 2.0,
                "float_market_value": 1_000_000_000.0,
                "source": "Tushare 实时日线",
                "updated_at": "2026-05-21T10:00:00",
            }
        ],
        ["code", "date"],
    )
    IntradayRadarService(db).record_snapshots(
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
                    "source": "Tushare 实时日线",
                    "freshness": "realtime",
                }
            ]
        ),
        sample_at=sample_at,
        trade_date="2026-05-21",
    )
    strategy_service = StrategyService(db)
    preset = strategy_service.save_preset(
        "盘中跟踪策略",
        {"min_amount": 20_000_000, "min_price": 4.0, "candidate_limit": 10},
    )
    service = IntradayRadarService(db)

    config = service.set_strategy_tracking_config(preset["id"], strategy_service)
    first_count = service.run_strategy_tracking(strategy_service, sample_at=sample_at)
    first = service.strategy_tracking_latest(strategy_service)
    strategy_service.save_preset(
        "盘中跟踪策略",
        {**preset["config"], "min_amount": 100_000_000, "candidate_limit": 10},
        preset_id=preset["id"],
    )
    second_count = service.run_strategy_tracking(strategy_service, sample_at=sample_at)
    second = service.strategy_tracking_latest(strategy_service)

    assert config["strategy_preset_id"] == preset["id"]
    assert first_count == 1
    assert first["config"]["strategy_preset_id"] == preset["id"]
    assert first["strategy"]["id"] == preset["id"]
    assert first["rows"][0]["code"] == "000001.SZ"
    assert first["rows"][0]["tracking_status"] == "new"
    assert second_count == 0
    assert second["config"]["strategy_preset_id"] == preset["id"]
    assert second["strategy"]["id"] == preset["id"]
    assert second["rows"] == []
    assert second["summary"]["zero_reason"]


def test_intraday_strategy_tracking_keeps_deleted_selection_unavailable(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    strategy_service = StrategyService(db)
    preset = strategy_service.save_preset("临时跟踪策略", {"min_amount": 20_000_000})
    service = IntradayRadarService(db)
    service.set_strategy_tracking_config(preset["id"], strategy_service)

    strategy_service.delete_preset(preset["id"])
    latest = service.strategy_tracking_latest(strategy_service)

    assert latest["config"]["strategy_preset_id"] == preset["id"]
    assert latest["config"]["strategy_status"] == "missing"
    assert latest["strategy"] is None
    assert latest["rows"] == []


def test_intraday_task_light_refresh_skips_board_radar_when_boards_are_disabled(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    radar_calls = []

    class ImmediateExecutor:
        def submit(self, fn, *args):
            fn(*args)

    monkeypatch.setattr(service, "executor", ImmediateExecutor())
    monkeypatch.setattr(
        service.intraday_service,
        "run_radar",
        lambda sample_at=None, config=None: radar_calls.append(sample_at) or 1,
    )
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
                    "source": "Tushare 实时日线",
                    "freshness": "realtime",
                }
            ]
        ),
    )

    task_id = service.start_intraday_sample({"sample_at": "2026-05-21T10:00:00", "mode": "light_refresh"})
    task = db.query("SELECT status, stage, summary_json FROM task_runs WHERE id = ?", [task_id])[0]
    summary = json.loads(task["summary_json"])

    assert radar_calls == []
    assert task["status"] == "completed_full"
    assert task["stage"] == "盘中轻量刷新完成"
    assert summary["mode"] == "light_refresh"
    assert summary["candidate_count"] == 0
    assert summary["snapshot_count"] == 1


def test_intraday_task_records_snapshot_and_runs_radar(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行")], ["code"])
    db.upsert("historical_bars", [_bar("000001.SZ", day) for day in range(1, 22)], ["code", "date"])
    IntradayRadarService(db).save_config(
        {
            "enabled_boards": {"anomaly": True},
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


def test_intraday_task_does_not_run_strategy_tracking_even_when_legacy_auto_flag_is_set(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行")], ["code"])
    db.upsert("historical_bars", [_bar("000001.SZ", day) for day in range(1, 22)], ["code", "date"])
    IntradayRadarService(db).save_config(
        {"enabled_boards": {"anomaly": True}, "min_amount": 0, "platform_bull_amount_advantage": 0, "candidate_limit": 10}
    )
    strategy_service = StrategyService(db)
    preset = strategy_service.save_preset(
        "盘中跟踪策略",
        {"min_amount": 20_000_000, "min_price": 4.0, "candidate_limit": 10},
    )
    IntradayRadarService(db).set_strategy_tracking_config(preset["id"], strategy_service)

    service = UpdateService(db)
    service.configure_runners(strategy_service=strategy_service)

    class ImmediateExecutor:
        def submit(self, fn, *args):
            fn(*args)

    monkeypatch.setattr(service, "executor", ImmediateExecutor())
    strategy_tracking_calls = []
    monkeypatch.setattr(service, "_intraday_strategy_tracking_auto_enabled", lambda: True, raising=False)
    monkeypatch.setattr(
        service.intraday_service,
        "run_strategy_tracking",
        lambda strategy_service, sample_at=None: strategy_tracking_calls.append(sample_at) or 1,
    )
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
                    "source": "Tushare 实时日线",
                    "freshness": "realtime",
                }
            ]
        ),
    )

    task_id = service.start_intraday_sample({"sample_at": "2026-05-21T10:00:00"})
    task = db.query("SELECT summary_json FROM task_runs WHERE id = ?", [task_id])[0]
    summary = json.loads(task["summary_json"])

    assert strategy_tracking_calls == []
    assert summary["strategy_tracking_count"] == 0
    assert summary["strategy_tracking_skipped_reason"] == "manual_only"


def test_manual_intraday_strategy_tracking_task_fetches_snapshot_and_runs_selected_strategy(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    strategy_service = StrategyService(db)
    preset = strategy_service.save_preset(
        "盘中跟踪策略",
        {"min_amount": 20_000_000, "min_price": 4.0, "candidate_limit": 10},
    )
    IntradayRadarService(db).set_strategy_tracking_config(preset["id"], strategy_service)
    service = UpdateService(db)
    service.configure_runners(strategy_service=strategy_service)
    tracking_calls = []

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
                    "source": "Tushare 实时日线",
                    "freshness": "realtime",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        service.intraday_service,
        "run_strategy_tracking",
        lambda strategy_service, sample_at=None: tracking_calls.append(sample_at) or 1,
    )

    task_id = service.start_intraday_strategy_tracking({"sample_at": "2026-05-21T10:00:00"})
    task = db.query("SELECT kind, status, stage, summary_json FROM task_runs WHERE id = ?", [task_id])[0]
    summary = json.loads(task["summary_json"])

    assert task["kind"] == "intraday_strategy_tracking"
    assert task["status"] == "completed_full"
    assert task["stage"] == "策略追踪完成"
    assert len(tracking_calls) == 1
    assert tracking_calls[0] == datetime(2026, 5, 21, 10, 0)
    assert summary["snapshot_count"] == 1
    assert summary["strategy_tracking_count"] == 1


def test_intraday_task_does_not_run_strategy_tracking_automatically_by_default(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行")], ["code"])
    db.upsert("historical_bars", [_bar("000001.SZ", day) for day in range(1, 22)], ["code", "date"])
    IntradayRadarService(db).save_config(
        {"enabled_boards": {"anomaly": True}, "min_amount": 0, "platform_bull_amount_advantage": 0, "candidate_limit": 10}
    )
    strategy_service = StrategyService(db)

    service = UpdateService(db)
    service.configure_runners(strategy_service=strategy_service)
    strategy_tracking_calls = []

    class ImmediateExecutor:
        def submit(self, fn, *args):
            fn(*args)

    monkeypatch.setattr(service, "executor", ImmediateExecutor())
    monkeypatch.setattr(
        service.intraday_service,
        "run_strategy_tracking",
        lambda strategy_service, sample_at=None: strategy_tracking_calls.append(sample_at) or 1,
    )
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
                    "source": "Tushare 实时日线",
                    "freshness": "realtime",
                }
            ]
        ),
    )

    task_id = service.start_intraday_sample({"sample_at": "2026-05-21T10:00:00"})
    task = db.query("SELECT status, warning, summary_json FROM task_runs WHERE id = ?", [task_id])[0]
    summary = json.loads(task["summary_json"])

    assert strategy_tracking_calls == []
    assert task["status"] == "completed_full"
    assert task["warning"] is None
    assert summary["strategy_tracking_count"] == 0
    assert summary["strategy_tracking_skipped_reason"] == "manual_only"
    assert summary["candidate_count"] == 1


def test_manual_intraday_strategy_tracking_fails_fast_when_memory_is_low(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    strategy_service = StrategyService(db)
    preset = strategy_service.save_preset("盘中跟踪策略", {"min_amount": 20_000_000, "candidate_limit": 10})
    IntradayRadarService(db).set_strategy_tracking_config(preset["id"], strategy_service)

    service = UpdateService(db)
    service.configure_runners(strategy_service=strategy_service)
    strategy_tracking_calls = []

    class ImmediateExecutor:
        def submit(self, fn, *args):
            fn(*args)

    monkeypatch.setattr(service, "executor", ImmediateExecutor())
    monkeypatch.setattr(service, "_available_memory_mb", lambda: 128, raising=False)
    monkeypatch.setattr(service, "_min_available_memory_mb", lambda: 700, raising=False)
    monkeypatch.setattr(
        service.intraday_service,
        "run_strategy_tracking",
        lambda strategy_service, sample_at=None: strategy_tracking_calls.append(sample_at) or 1,
    )

    task_id = service.start_intraday_strategy_tracking({"sample_at": "2026-05-21T10:00:00"})
    task = db.query("SELECT status, warning, error_message FROM task_runs WHERE id = ?", [task_id])[0]

    assert strategy_tracking_calls == []
    assert task["status"] == "failed"
    assert "可用内存不足" in task["warning"]
    assert "可用内存不足" in task["error_message"]


def test_intraday_task_rejects_frame_date_mismatch_unless_forced(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    task_id = "intraday-stale"
    service._write_task(task_id, kind="intraday", status="running", stage="启动")
    stale_frame = pd.DataFrame(
        [
            {
                "code": "000001.SZ",
                "date": "2026-05-22",
                "name": "平安银行",
                "latest_price": 10.55,
                "pct_chg": 4.2,
                "high": 10.6,
                "low": 9.9,
                "volume": 3_100_000.0,
                "amount": 62_000_000.0,
                "source": "Tushare 实时日线",
                "freshness": "realtime",
            }
        ]
    )
    monkeypatch.setattr(service, "_fetch_intraday_snapshot_frame", lambda include_bj, exclude_star, warnings: stale_frame)

    service._run_intraday_sample(task_id, {"sample_at": "2026-05-23T10:00:00"})

    task = db.query("SELECT status, error_message FROM task_runs WHERE id = ?", [task_id])[0]
    assert task["status"] == "failed"
    assert "快照日期" in task["error_message"]
    assert db.scalar("SELECT COUNT(*) FROM intraday_snapshots") == 0

    forced_task_id = "intraday-stale-force"
    service._write_task(forced_task_id, kind="intraday", status="running", stage="启动")
    service._run_intraday_sample(forced_task_id, {"sample_at": "2026-05-23T10:00:00", "force": True})
    forced_task = db.query("SELECT status FROM task_runs WHERE id = ?", [forced_task_id])[0]
    assert forced_task["status"] == "completed_full"
    assert db.scalar("SELECT COUNT(*) FROM intraday_snapshots") == 1


def test_intraday_task_refreshes_market_environment_and_concept_heat(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行"), _stock("000002.SZ", "万科A")], ["code"])
    db.upsert("historical_bars", [_bar("000001.SZ", day) for day in range(1, 22)], ["code", "date"])
    db.upsert("historical_bars", [_bar("000002.SZ", day, close=8.0) for day in range(1, 22)], ["code", "date"])
    db.upsert(
        "tushare_ths_member",
        [
            {"code": "000001.SZ", "name": "平安银行", "con_code": "885001.TI", "con_name": "测试概念", "source": "test"},
            {"code": "000002.SZ", "name": "万科A", "con_code": "885001.TI", "con_name": "测试概念", "source": "test"},
        ],
        ["code", "con_code"],
    )
    IntradayRadarService(db).save_config({"min_amount": 0, "platform_bull_amount_advantage": 0, "candidate_limit": 10})

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
                },
                {
                    "code": "000002.SZ",
                    "name": "万科A",
                    "latest_price": 8.8,
                    "pct_chg": 6.1,
                    "high": 8.9,
                    "low": 8.1,
                    "volume": 2_500_000.0,
                    "amount": 44_000_000.0,
                    "source": "AkShare 新浪",
                },
            ]
        ),
    )

    task_id = service.start_intraday_sample({"sample_at": "2026-05-21T10:00:00"})
    task = db.query("SELECT summary_json FROM task_runs WHERE id = ?", [task_id])[0]
    market = db.query("SELECT * FROM market_environment WHERE date = ?", ["2026-05-21"])[0]
    sector = db.query("SELECT * FROM market_sector_daily WHERE trade_date = ? AND sector_code = ?", ["2026-05-21", "885001.TI"])[0]
    summary = json.loads(task["summary_json"])

    assert summary["market_environment_count"] == 1
    assert summary["sector_heat_count"] == 1
    assert market["up_count"] == 2
    assert market["strong_count"] == 1
    assert sector["sector_name"] == "测试概念"
    assert sector["member_count"] == 2
    assert sector["strong_count"] == 1
    assert sector["source"] == "实时快照概念热度"


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
    frame = service._fetch_intraday_snapshot_frame(include_bj=False, exclude_star=False, warnings=[])

    assert frame.iloc[0]["source"] == "Tushare 实时日线"


def test_intraday_snapshot_rejects_daily_fallback_freshness(tmp_path, monkeypatch):
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
                        "source": "Tushare 日线回退",
                        "freshness": "daily_fallback",
                    }
                ]
            )

    monkeypatch.setattr("backend.app.services.update_service.TushareRealtimeSource", FakeTushareSource)

    with pytest.raises(RuntimeError, match="非盘中实时"):
        service._fetch_intraday_snapshot_frame(include_bj=False, exclude_star=False, warnings=[])


def test_daily_update_snapshot_prefers_tushare_realtime(tmp_path, monkeypatch):
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
                        "turnover_rate": 1.3,
                        "float_market_value": 120_000_000_000.0,
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
    count = service._update_snapshots(force=True, include_bj=False, exclude_star=False, warnings=[])
    row = db.query("SELECT * FROM daily_snapshots WHERE code = '000001.SZ'")[0]

    assert count == 1
    assert str(row["date"]).startswith("2026-05-21")
    assert row["source"] == "Tushare 实时日线"
    assert row["float_market_value"] == 120_000_000_000.0


def test_intraday_cleanup_deletes_old_rows_after_history_exists(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    old_sample = datetime(2026, 5, 10, 10, 0)
    recent_sample = datetime(2026, 5, 24, 10, 0)
    for sample_at in [old_sample, recent_sample]:
        db.upsert(
            "intraday_snapshots",
            [
                {
                    "code": "000001.SZ",
                    "trade_date": sample_at.date(),
                    "sample_at": sample_at,
                    "name": "平安银行",
                    "latest_price": 10.0,
                    "pct_chg": 1.0,
                    "high": 10.2,
                    "low": 9.9,
                    "volume": 100,
                    "amount": 1000000,
                    "source": "test",
                    "created_at": sample_at,
                }
            ],
            ["code", "sample_at"],
        )
        ranking = {
            "sample_at": sample_at,
            "trade_date": sample_at.date(),
            "rank": 1,
            "code": "000001.SZ",
            "name": "平安银行",
            "status": "test",
            "radar_score": 80,
            "latest_price": 10.0,
            "pct_chg": 1.0,
            "amount": 1000000,
            "volume": 100,
            "distance_to_upper": 0,
            "breakout_clearance": 0,
            "amount_delta": 0,
            "volume_delta": 0,
            "amount_ratio": 1,
            "price_change": 0,
            "source": "test",
            "reasons_json": "[]",
            "metrics_json": "{}",
            "created_at": sample_at,
        }
        db.upsert("intraday_radar_candidates", [ranking], ["sample_at", "code"])
        db.upsert(
            "intraday_radar_rankings",
            [{**ranking, "radar_mode": "score"}],
            ["sample_at", "radar_mode", "code"],
        )
    db.upsert(
        "historical_bars",
        [
            {
                "code": "000001.SZ",
                "date": old_sample.date(),
                "open": 10,
                "high": 10,
                "low": 9,
                "close": 10,
                "prev_close": 9.8,
                "volume": 100,
                "amount": 1000000,
                "turn": 1,
                "pct_chg": 1,
                "tradestatus": "1",
                "is_st": False,
                "source": "test",
                "updated_at": old_sample,
            }
        ],
        ["code", "date"],
    )

    deleted = service.cleanup_intraday_history(retention_days=10, now=datetime(2026, 5, 25, 8, 0))

    assert deleted["intraday_snapshots"] == 1
    assert deleted["intraday_radar_candidates"] == 1
    assert deleted["intraday_radar_rankings"] == 1
    assert db.scalar("SELECT COUNT(*) FROM intraday_snapshots WHERE sample_at = ?", [old_sample]) == 0
    assert db.scalar("SELECT COUNT(*) FROM intraday_snapshots WHERE sample_at = ?", [recent_sample]) == 1
    assert db.scalar("SELECT COUNT(*) FROM intraday_radar_rankings WHERE sample_at = ?", [old_sample]) == 0
