from datetime import date, timedelta

import pandas as pd
import pytest

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.data_service import DataService
from backend.app.services.analysis_service import AnalysisService
from backend.app.services.backtest_service import BacktestService, compute_forward_labels
from backend.app.services.strategy_service import DEFAULT_STRATEGY_CONFIG


def test_analysis_frame_as_of_date_uses_history_without_latest_snapshot(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "stock_basic",
        [
            {
                "code": "000001.SZ",
                "name": "平安银行",
                "exchange": "SZ",
                "list_date": "1991-04-03",
                "source": "test",
                "is_st": False,
                "suspended": False,
                "updated_at": "2026-01-01T00:00:00",
            }
        ],
        ["code"],
    )
    start = date(2026, 1, 1)
    bars = []
    for index in range(35):
        day = start + timedelta(days=index)
        close = 10 + index
        bars.append(
            {
                "code": "000001.SZ",
                "date": day,
                "open": close - 0.2,
                "high": close + 0.4,
                "low": close - 0.5,
                "close": close,
                "prev_close": close - 1 if index else close,
                "volume": 1000 + index,
                "amount": 10_000 + index,
                "turn": 2.0,
                "pct_chg": 1.23,
                "tradestatus": "1",
                "is_st": False,
                "source": "Baostock",
                "updated_at": "2026-01-01T00:00:00",
            }
        )
    db.upsert("historical_bars", bars, ["code", "date"])
    db.upsert(
        "daily_snapshots",
        [
            {
                "code": "000001.SZ",
                "date": "2026-02-20",
                "name": "未来快照",
                "latest_price": 999.0,
                "pct_chg": 88.0,
                "high": 999.0,
                "low": 999.0,
                "volume": 999_000.0,
                "amount": 999_000_000.0,
                "turnover_rate": 99.0,
                "float_market_value": 999_000_000_000.0,
                "source": "AkShare 新浪",
                "updated_at": "2026-02-20T10:00:00",
            }
        ],
        ["code", "date"],
    )

    frame = AnalysisService(db)._build_analysis_frame(
        {**DEFAULT_STRATEGY_CONFIG, "ma_short_window": 5, "ma_long_window": 10},
        as_of_date=date(2026, 1, 20),
    )
    row = frame.iloc[0]

    assert row["latest_price"] == 29
    assert row["pct_chg"] == 1.23
    assert row["volume"] == 1019
    assert row["name"] == "平安银行"
    assert row["data_sources"]["snapshot"] is None


def test_forward_labels_use_next_trading_open_and_future_bars():
    start = date(2026, 1, 1)
    rows = []
    for index in range(25):
        day = start + timedelta(days=index)
        is_future = day > date(2026, 1, 5)
        future_index = (day - date(2026, 1, 5)).days if is_future else 0
        close = 10 + future_index * 0.1 if is_future else 9.8
        rows.append(
            {
                "code": "000001.SZ",
                "date": day,
                "open": 10.0 if is_future else 9.7,
                "high": close + 0.1,
                "low": 9.4 if future_index == 3 else close - 0.2,
                "close": close,
            }
        )

    labels = compute_forward_labels(
        pd.DataFrame(rows),
        "000001.SZ",
        date(2026, 1, 5),
    )

    assert labels["entry_date"] == date(2026, 1, 6)
    assert labels["entry_price"] == 10.0
    assert labels["return_5d"] == pytest.approx(0.05)
    assert labels["return_10d"] == pytest.approx(0.10)
    assert labels["return_20d"] == pytest.approx(0.20)
    assert labels["max_return_10d"] == pytest.approx(0.11)
    assert labels["max_drawdown_10d"] == pytest.approx(-0.06)
    assert labels["hit_5pct_10d"] is True
    assert labels["hit_8pct_10d"] is True
    assert labels["hit_stop_5pct_10d"] is True


def test_data_service_returns_latest_backtest_result(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "backtest_runs",
        [
            {
                "id": "backtest-1",
                "status": "completed_full",
                "started_at": "2026-01-01T10:00:00",
                "finished_at": "2026-01-01T10:05:00",
                "config_json": '{"signal_mode": "platform_setup"}',
                "summary_json": '{"signal_count": 1, "avg_return_10d": 0.08}',
                "error_message": None,
            }
        ],
        ["id"],
    )
    db.upsert(
        "backtest_signals",
        [
            {
                "run_id": "backtest-1",
                "as_of_date": "2026-01-01",
                "rank": 1,
                "code": "000001.SZ",
                "name": "平安银行",
                "latest_price": 10.0,
                "signal_type": "平台临界",
                "signal_score": 88.0,
                "reasons_json": '["接近上沿"]',
                "metrics_json": '{"rps20": 80}',
                "entry_date": "2026-01-02",
                "entry_price": 10.1,
                "return_5d": 0.04,
                "return_10d": 0.08,
                "return_20d": 0.12,
                "max_return_10d": 0.1,
                "max_drawdown_10d": -0.03,
                "hit_5pct_10d": True,
                "hit_8pct_10d": True,
                "hit_stop_5pct_10d": False,
                "created_at": "2026-01-01T10:05:00",
            }
        ],
        ["run_id", "as_of_date", "code"],
    )

    result = DataService(db).backtest_result()

    assert result["run"]["id"] == "backtest-1"
    assert result["run"]["summary"]["signal_count"] == 1
    assert result["signals"][0]["reasons"] == ["接近上沿"]
    assert result["signals"][0]["metrics"]["rps20"] == 80


def test_data_service_can_return_saved_backtest_report_by_run_id(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "backtest_runs",
        [
            {
                "id": "backtest-old",
                "status": "completed_full",
                "started_at": "2026-01-01T10:00:00",
                "finished_at": "2026-01-01T10:05:00",
                "config_json": '{"signal_mode": "platform_setup"}',
                "summary_json": '{"signal_count": 1}',
                "error_message": None,
            },
            {
                "id": "backtest-new",
                "status": "completed_full",
                "started_at": "2026-01-02T10:00:00",
                "finished_at": "2026-01-02T10:05:00",
                "config_json": '{"signal_mode": "platform_breakout"}',
                "summary_json": '{"signal_count": 1}',
                "error_message": None,
            },
        ],
        ["id"],
    )
    for run_id, signal_date, code in [
        ("backtest-old", "2026-01-01", "000001.SZ"),
        ("backtest-new", "2026-01-02", "000002.SZ"),
    ]:
        db.upsert(
            "backtest_signals",
            [
                {
                    "run_id": run_id,
                    "as_of_date": signal_date,
                    "rank": 1,
                    "code": code,
                    "name": code,
                    "latest_price": 10.0,
                    "signal_type": "平台突破观察",
                    "signal_score": 80.0,
                    "reasons_json": "[]",
                    "metrics_json": "{}",
                    "entry_date": None,
                    "entry_price": None,
                    "return_5d": None,
                    "return_10d": None,
                    "return_20d": None,
                    "max_return_10d": None,
                    "max_drawdown_10d": None,
                    "hit_5pct_10d": None,
                    "hit_8pct_10d": None,
                    "hit_stop_5pct_10d": None,
                    "created_at": "2026-01-01T10:05:00",
                }
            ],
            ["run_id", "as_of_date", "code"],
        )

    service = DataService(db)
    runs = service.backtest_runs()
    old = service.backtest_result("backtest-old")

    assert [run["id"] for run in runs[:2]] == ["backtest-new", "backtest-old"]
    assert old["run"]["id"] == "backtest-old"
    assert old["signals"][0]["code"] == "000001.SZ"


def test_backtest_latest_float_market_value_policy_uses_newer_proxy_for_history(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "stock_basic",
        [
            {
                "code": "000001.SZ",
                "name": "平安银行",
                "exchange": "SZ",
                "list_date": "1991-04-03",
                "source": "test",
                "is_st": False,
                "suspended": False,
                "updated_at": "2026-01-01T00:00:00",
            }
        ],
        ["code"],
    )
    start = date(2026, 1, 1)
    db.upsert(
        "historical_bars",
        [
            {
                "code": "000001.SZ",
                "date": start + timedelta(days=index),
                "open": 10 + index * 0.1,
                "high": 10.3 + index * 0.1,
                "low": 9.8 + index * 0.1,
                "close": 10.1 + index * 0.1,
                "prev_close": 10 + index * 0.1,
                "volume": 1000 + index,
                "amount": 200_000_000,
                "turn": 2.0,
                "pct_chg": 1.0,
                "tradestatus": "1",
                "is_st": False,
                "source": "Baostock",
                "updated_at": "2026-01-01T00:00:00",
            }
            for index in range(35)
        ],
        ["code", "date"],
    )
    db.upsert(
        "float_market_values",
        [
            {
                "code": "000001.SZ",
                "date": "2026-02-20",
                "float_shares": 1_000_000_000,
                "float_market_value": 12_000_000_000,
                "source": "latest proxy",
                "updated_at": "2026-02-20T00:00:00",
            }
        ],
        ["code", "date"],
    )

    base_strategy = {
        **DEFAULT_STRATEGY_CONFIG,
        "ma_short_window": 5,
        "ma_long_window": 10,
        "min_float_market_value": 10_000_000_000,
        "max_float_market_value": 20_000_000_000,
        "missing_float_market_value_policy": "skip",
    }
    regular = AnalysisService(db)._build_analysis_frame(base_strategy, as_of_date=date(2026, 1, 20))
    proxied = AnalysisService(db)._build_analysis_frame(
        {**base_strategy, "_backtest_float_market_value_policy": "latest_proxy"},
        as_of_date=date(2026, 1, 20),
    )

    assert regular.iloc[0]["float_market_value"] is None
    assert proxied.iloc[0]["float_market_value"] == 12_000_000_000


def test_backtest_service_runs_one_historical_date(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "stock_basic",
        [
            {
                "code": "000001.SZ",
                "name": "平安银行",
                "exchange": "SZ",
                "list_date": "1991-04-03",
                "source": "test",
                "is_st": False,
                "suspended": False,
                "updated_at": "2026-01-01T00:00:00",
            }
        ],
        ["code"],
    )
    start = date(2026, 1, 1)
    rows = []
    for index in range(30):
        day = start + timedelta(days=index)
        close = 10 + index * 0.1
        rows.append(
            {
                "code": "000001.SZ",
                "date": day,
                "open": close - 0.05,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "prev_close": close - 0.1 if index else close,
                "volume": 1000 + index,
                "amount": 100_000 + index,
                "turn": 2.0,
                "pct_chg": 1.0,
                "tradestatus": "1",
                "is_st": False,
                "source": "Baostock",
                "updated_at": "2026-01-01T00:00:00",
            }
        )
    db.upsert("historical_bars", rows, ["code", "date"])

    run_id = BacktestService(db).run(
        {
            "start_date": "2026-01-10",
            "end_date": "2026-01-10",
            "step": 1,
            "candidate_limit": 1,
            "config": {
                "analysis_mode": "score",
                "signal_mode": "breakout_or_pullback",
                "min_price": 0,
                "min_amount": 0,
                "min_float_market_value": None,
                "max_float_market_value": None,
                "min_rps20": None,
                "min_rps60": None,
                "min_rps120": None,
                "min_turnover": None,
                "max_turnover": None,
                "min_pct_chg": None,
                "max_pct_chg": None,
                "volume_ratio_min": None,
                "max_ma_distance": None,
                "candidate_limit": 1,
                "missing_turnover_policy": "allow",
                "missing_float_market_value_policy": "allow",
                "include_bj": False,
                "exclude_star_board": False,
            },
        },
        run_id="backtest-test",
    )

    result = DataService(db).backtest_result(run_id)

    assert result["run"]["status"] == "completed_full"
    assert result["run"]["summary"]["signal_count"] == 1
    assert result["signals"][0]["code"] == "000001.SZ"
    assert result["signals"][0]["return_5d"] is not None


def test_portfolio_backtest_accepts_initial_capital_payload_alias(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "stock_basic",
        [
            {
                "code": "000001.SZ",
                "name": "平安银行",
                "exchange": "SZ",
                "list_date": "1991-04-03",
                "source": "test",
                "is_st": False,
                "suspended": False,
                "updated_at": "2026-01-01T00:00:00",
            }
        ],
        ["code"],
    )
    start = date(2026, 1, 1)
    db.upsert(
        "historical_bars",
        [
            {
                "code": "000001.SZ",
                "date": start + timedelta(days=index),
                "open": 10 + index * 0.1,
                "high": 10.3 + index * 0.1,
                "low": 9.8 + index * 0.1,
                "close": 10.1 + index * 0.1,
                "prev_close": 10 + index * 0.1,
                "volume": 1000 + index,
                "amount": 200_000_000,
                "turn": 2.0,
                "pct_chg": 1.0,
                "tradestatus": "1",
                "is_st": False,
                "source": "Baostock",
                "updated_at": "2026-01-01T00:00:00",
            }
            for index in range(40)
        ],
        ["code", "date"],
    )

    result = BacktestService(db).run_portfolio_backtest(
        {
            "start_date": "2026-01-10",
            "end_date": "2026-01-12",
            "step": 1,
            "candidate_limit": 1,
            "max_positions": 1,
            "hold_days": 2,
            "initial_capital": 250_000,
            "config": {
                "analysis_mode": "score",
                "min_price": 0,
                "min_amount": 0,
                "min_float_market_value": None,
                "max_float_market_value": None,
                "min_rps20": None,
                "min_rps60": None,
                "min_rps120": None,
                "min_turnover": None,
                "max_turnover": None,
                "min_pct_chg": None,
                "max_pct_chg": None,
                "volume_ratio_min": None,
                "max_ma_distance": None,
                "candidate_limit": 1,
                "missing_turnover_policy": "allow",
                "missing_float_market_value_policy": "allow",
                "include_bj": False,
                "exclude_star_board": False,
            },
        },
        run_id="portfolio-initial-capital",
    )

    assert result["run"]["summary"]["initial_equity"] == 250_000
    assert result["run"]["config"]["initial_equity"] == 250_000
