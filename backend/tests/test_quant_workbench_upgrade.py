import json
import sys
from datetime import date, datetime, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.backtest_service import BacktestService
from backend.app.services.data_service import DataService
from backend.app.services.intraday_service import IntradayRadarService
from backend.app.services.update_service import DEFAULT_DATA_DAG, UpdateService
from backend.app.services.watchlist_service import WatchlistService


def _stock(code: str, name: str | None = None) -> dict:
    return {
        "code": code,
        "name": name or code,
        "exchange": code.split(".")[-1],
        "list_date": "2020-01-01",
        "source": "test",
        "is_st": False,
        "suspended": False,
        "updated_at": "2026-05-22T09:00:00",
    }


def _bar(code: str, day: date, close: float, pct_chg: float = 1.0, amount: float = 10_000_000.0) -> dict:
    return {
        "code": code,
        "date": day,
        "open": close - 0.1,
        "high": close + 0.3,
        "low": close - 0.2,
        "close": close,
        "prev_close": close / (1 + pct_chg / 100),
        "volume": 1_000_000.0,
        "amount": amount,
        "turn": 2.0,
        "pct_chg": pct_chg,
        "tradestatus": "1",
        "is_st": False,
        "source": "test",
        "updated_at": "2026-05-22T16:00:00",
    }


def _seed_market(db: Database) -> None:
    trade_date = date(2026, 5, 22)
    db.upsert(
        "stock_basic",
        [_stock("000001.SZ", "平安银行"), _stock("600000.SH", "浦发银行")],
        ["code"],
    )
    rows = []
    for offset in range(24):
        day = trade_date - timedelta(days=23 - offset)
        rows.append(_bar("000001.SZ", day, 10 + offset * 0.12, pct_chg=1.2, amount=30_000_000))
        rows.append(_bar("600000.SH", day, 9 + offset * 0.05, pct_chg=-0.4 if offset == 23 else 0.3, amount=18_000_000))
    db.upsert("historical_bars", rows, ["code", "date"])
    UpdateService(db)._update_market_environment(trade_date, source=FakeIndexSource())


class FakeIndexSource:
    def fetch_index_daily(self, index_codes, trade_date):
        return pd.DataFrame(
            [
                {
                    "index_code": code,
                    "trade_date": trade_date.isoformat(),
                    "pct_chg": 1.2,
                    "amount": 100_000_000.0,
                    "source": "Tushare index_daily",
                    "updated_at": "2026-05-22T16:00:00",
                }
                for code in index_codes[:2]
            ]
        )


def test_schema_adds_quant_workbench_tables(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)

    tables = {
        row["table_name"]
        for row in db.query(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main'
            """
        )
    }

    assert {
        "update_checkpoints",
        "market_sector_daily",
        "factor_values",
        "factor_definitions",
        "watchlist_hypotheses",
    }.issubset(tables)


def test_market_overview_uses_environment_and_sector_heatmap(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    _seed_market(db)
    db.upsert(
        "market_sector_daily",
        [
            {
                "sector_code": "885800.TI",
                "sector_name": "半导体设备",
                "sector_type": "concept",
                "trade_date": "2026-05-22",
                "pct_chg": 3.2,
                "amount": 1_200_000_000.0,
                "net_amount": 210_000_000.0,
                "company_count": 42,
                "limit_up_count": 3,
                "strong_count": 9,
                "leader_code": "000001.SZ",
                "leader_name": "平安银行",
                "heat_score": 86.5,
                "source": "test",
                "updated_at": "2026-05-22T16:00:00",
            }
        ],
        ["sector_code", "sector_type", "trade_date"],
    )

    overview = DataService(db).market_overview()
    heatmap = DataService(db).sector_heatmap("concept")

    assert overview["state"]["label"] in {"强势", "回暖", "震荡", "偏弱", "退潮", "极端风险"}
    assert overview["state"]["suggested_position"] in {"0%-20%", "20%-40%", "40%-60%", "60%-80%", "80%-100%"}
    assert overview["pulse"]["risk_level"] in {"低", "中", "高", "极高"}
    assert overview["sector_heatmap"][0]["name"] == "半导体设备"
    assert overview["sector_heatmap"][0]["limit_up_count_status"] == "computed"
    assert overview["action_items"]
    assert heatmap[0]["heat_score"] == 86.5


def test_market_actions_do_not_warn_when_freshness_is_normal(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    _seed_market(db)
    trade_date = date(2026, 5, 22)
    db.upsert(
        "daily_snapshots",
        [
            {
                "code": "000001.SZ",
                "date": trade_date,
                "name": "平安银行",
                "latest_price": 10.0,
                "pct_chg": 1.0,
                "high": 10.2,
                "low": 9.8,
                "volume": 1_000_000,
                "amount": 30_000_000,
                "turnover_rate": 2.0,
                "float_market_value": 100_000_000,
                "source": "test",
                "updated_at": "2026-05-22T16:00:00",
            }
        ],
        ["code", "date"],
    )
    db.upsert(
        "tushare_daily_basic",
        [
            {
                "code": "000001.SZ",
                "trade_date": trade_date,
                "close": 10.0,
                "turnover_rate": 2.0,
                "updated_at": "2026-05-22T16:00:00",
            }
        ],
        ["code", "trade_date"],
    )
    db.upsert(
        "market_sector_daily",
        [
            {
                "sector_code": "885800.TI",
                "sector_name": "半导体设备",
                "sector_type": "concept",
                "trade_date": trade_date,
                "pct_chg": 3.2,
                "amount": 1_200_000_000.0,
                "net_amount": 210_000_000.0,
                "company_count": 42,
                "limit_up_count": 3,
                "limit_up_count_status": "computed",
                "strong_count": 9,
                "strong_count_status": "computed",
                "leader_code": "000001.SZ",
                "leader_name": "平安银行",
                "heat_score": 86.5,
                "source": "test",
                "updated_at": "2026-05-22T16:00:00",
            }
        ],
        ["sector_code", "sector_type", "trade_date"],
    )

    actions = DataService(db).market_overview()["action_items"]

    assert all(action["id"] != "data-stale" for action in actions)


def test_sector_persist_fills_limit_and_strong_counts(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    trade_date = date(2026, 5, 22)
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行"), _stock("000002.SZ", "万科A")], ["code"])
    db.upsert(
        "tushare_ths_member",
        [
            {
                "code": "000001.SZ",
                "name": "平安银行",
                "con_code": "885800.TI",
                "con_name": "半导体设备",
                "weight": None,
                "in_date": "2020-01-01",
                "out_date": None,
                "is_new": "Y",
                "source": "test",
                "updated_at": "2026-05-22T09:00:00",
            },
            {
                "code": "000001.SZ",
                "name": "平安银行",
                "con_code": "881100.TI",
                "con_name": "银行",
                "weight": None,
                "in_date": "2020-01-01",
                "out_date": None,
                "is_new": "Y",
                "source": "test",
                "updated_at": "2026-05-22T09:00:00",
            },
            {
                "code": "000002.SZ",
                "name": "万科A",
                "con_code": "885800.TI",
                "con_name": "半导体设备",
                "weight": None,
                "in_date": "2020-01-01",
                "out_date": None,
                "is_new": "Y",
                "source": "test",
                "updated_at": "2026-05-22T09:00:00",
            },
            {
                "code": "000002.SZ",
                "name": "万科A",
                "con_code": "881100.TI",
                "con_name": "银行",
                "weight": None,
                "in_date": "2020-01-01",
                "out_date": None,
                "is_new": "Y",
                "source": "test",
                "updated_at": "2026-05-22T09:00:00",
            },
        ],
        ["code", "con_code"],
    )
    db.upsert(
        "daily_snapshots",
        [
            {
                "code": "000001.SZ",
                "date": trade_date,
                "name": "平安银行",
                "latest_price": 10.0,
                "pct_chg": 9.8,
                "high": 10.1,
                "low": 9.5,
                "volume": 1_000_000.0,
                "amount": 20_000_000.0,
                "turnover_rate": 2.0,
                "float_market_value": 1_000_000_000.0,
                "source": "test",
                "updated_at": "2026-05-22T15:00:00",
            },
            {
                "code": "000002.SZ",
                "date": trade_date,
                "name": "万科A",
                "latest_price": 11.0,
                "pct_chg": 5.2,
                "high": 11.1,
                "low": 10.5,
                "volume": 1_000_000.0,
                "amount": 20_000_000.0,
                "turnover_rate": 2.0,
                "float_market_value": 1_000_000_000.0,
                "source": "test",
                "updated_at": "2026-05-22T15:00:00",
            },
        ],
        ["code", "date"],
    )
    db.upsert(
        "tushare_limit_list_d",
        [
            {
                "code": "000001.SZ",
                "trade_date": trade_date,
                "name": "平安银行",
                "close": 10.0,
                "pct_chg": 9.8,
                "limit_type": "U",
                "up_stat": None,
                "fd_amount": 1_000_000.0,
                "first_time": "09:45",
                "last_time": "14:55",
                "open_times": 0,
                "source": "test",
                "updated_at": "2026-05-22T15:00:00",
            }
        ],
        ["code", "trade_date"],
    )
    frame = pd.DataFrame(
        [
            {
                "sector_code": "885800.TI",
                "sector_name": "半导体设备",
                "sector_type": "concept",
                "trade_date": trade_date,
                "pct_chg": 2.5,
                "amount": None,
                "net_amount": 100_000_000.0,
                "company_count": 2,
                "limit_up_count": None,
                "strong_count": None,
                "leader_code": None,
                "leader_name": None,
                "heat_score": 80.0,
                "source": "test",
                "updated_at": "2026-05-22T15:00:00",
            },
            {
                "sector_code": "881100.TI",
                "sector_name": "银行",
                "sector_type": "industry",
                "trade_date": trade_date,
                "pct_chg": 1.8,
                "amount": None,
                "net_amount": 80_000_000.0,
                "company_count": 2,
                "limit_up_count": None,
                "strong_count": None,
                "leader_code": None,
                "leader_name": None,
                "heat_score": 70.0,
                "source": "test",
                "updated_at": "2026-05-22T15:00:00",
            },
        ]
    )

    assert UpdateService(db)._persist_sector_frames([frame]) == 2
    row = db.query("SELECT * FROM market_sector_daily WHERE sector_code = '885800.TI'")[0]
    industry = db.query("SELECT * FROM market_sector_daily WHERE sector_code = '881100.TI'")[0]
    assert row["limit_up_count"] == 1
    assert row["limit_up_count_status"] == "computed"
    assert row["strong_count"] == 2
    assert row["strong_count_status"] == "computed"
    assert row["leader_code"] == "000001.SZ"
    assert row["leader_pct_chg"] == 9.8
    assert industry["limit_up_count"] == 1
    assert industry["limit_up_count_status"] == "computed"
    assert industry["strong_count_status"] == "computed"
    assert DataService(db).sector_heatmap("industry")[0]["limit_up_count_status"] == "computed"


def test_existing_sector_rows_refresh_not_computed_counts_with_recent_available_dates(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    sector_date = date(2026, 5, 28)
    quote_date = date(2026, 5, 27)
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行"), _stock("000002.SZ", "万科A")], ["code"])
    db.upsert(
        "tushare_ths_member",
        [
            {
                "code": "000001.SZ",
                "name": "平安银行",
                "con_code": "885800.TI",
                "con_name": "半导体设备",
                "weight": None,
                "in_date": "2020-01-01",
                "out_date": None,
                "is_new": "Y",
                "source": "test",
                "updated_at": "2026-05-28T09:00:00",
            },
            {
                "code": "000002.SZ",
                "name": "万科A",
                "con_code": "885800.TI",
                "con_name": "半导体设备",
                "weight": None,
                "in_date": "2020-01-01",
                "out_date": None,
                "is_new": "Y",
                "source": "test",
                "updated_at": "2026-05-28T09:00:00",
            },
        ],
        ["code", "con_code"],
    )
    db.upsert(
        "historical_bars",
        [
            _bar("000001.SZ", quote_date, 10.0, pct_chg=10.0),
            _bar("000002.SZ", quote_date, 11.0, pct_chg=5.5),
        ],
        ["code", "date"],
    )
    db.upsert(
        "tushare_limit_list_d",
        [
            {
                "code": "000001.SZ",
                "trade_date": quote_date,
                "name": "平安银行",
                "close": 10.0,
                "pct_chg": 10.0,
                "limit_type": "U",
                "up_stat": None,
                "fd_amount": 1_000_000.0,
                "first_time": "09:45",
                "last_time": "14:55",
                "open_times": 0,
                "source": "test",
                "updated_at": "2026-05-27T15:00:00",
            }
        ],
        ["code", "trade_date"],
    )
    db.upsert(
        "market_sector_daily",
        [
            {
                "sector_code": "885800.TI",
                "sector_name": "半导体设备",
                "sector_type": "concept",
                "trade_date": sector_date,
                "pct_chg": 2.5,
                "amount": None,
                "net_amount": 100_000_000.0,
                "company_count": 2,
                "limit_up_count": None,
                "limit_up_count_status": "not_computed",
                "strong_count": None,
                "strong_count_status": "not_computed",
                "leader_code": None,
                "leader_name": None,
                "leader_pct_chg": None,
                "heat_score": 80.0,
                "source": "test",
                "updated_at": "2026-05-28T15:00:00",
            }
        ],
        ["sector_code", "sector_type", "trade_date"],
    )

    UpdateService(db)._update_market_sector_daily(sector_date, object(), [])

    row = db.query("SELECT * FROM market_sector_daily WHERE sector_code = '885800.TI'")[0]
    assert row["limit_up_count_status"] == "computed"
    assert row["limit_up_count"] == 1
    assert row["strong_count_status"] == "computed"
    assert row["strong_count"] == 2
    assert row["leader_code"] == "000001.SZ"
    assert row["member_count"] == 2
    assert row["limit_data_date"] == quote_date
    assert row["quote_data_date"] == quote_date


def test_sector_breadth_reports_missing_members_instead_of_zero_counts(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    sector_date = date(2026, 5, 28)
    db.upsert(
        "market_sector_daily",
        [
            {
                "sector_code": "881100.TI",
                "sector_name": "银行",
                "sector_type": "industry",
                "trade_date": sector_date,
                "pct_chg": 1.5,
                "amount": None,
                "net_amount": 80_000_000.0,
                "company_count": 25,
                "limit_up_count": None,
                "limit_up_count_status": "not_computed",
                "strong_count": None,
                "strong_count_status": "not_computed",
                "leader_code": None,
                "leader_name": None,
                "leader_pct_chg": None,
                "heat_score": 70.0,
                "source": "test",
                "updated_at": "2026-05-28T15:00:00",
            }
        ],
        ["sector_code", "sector_type", "trade_date"],
    )

    UpdateService(db)._update_market_sector_daily(sector_date, object(), [])
    row = DataService(db).sector_heatmap("industry")[0]

    assert row["limit_up_count"] is None
    assert row["limit_up_count_status"] == "missing_members"
    assert row["strong_count"] is None
    assert row["strong_count_status"] == "missing_members"
    assert row["member_count"] == 0


def test_sector_breadth_reports_missing_limit_and_quote_dates(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    sector_date = date(2026, 5, 28)
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行")], ["code"])
    db.upsert(
        "tushare_ths_member",
        [
            {
                "code": "000001.SZ",
                "name": "平安银行",
                "con_code": "885800.TI",
                "con_name": "半导体设备",
                "weight": None,
                "in_date": "2020-01-01",
                "out_date": None,
                "is_new": "Y",
                "source": "test",
                "updated_at": "2026-05-28T09:00:00",
            }
        ],
        ["code", "con_code"],
    )
    db.upsert(
        "market_sector_daily",
        [
            {
                "sector_code": "885800.TI",
                "sector_name": "半导体设备",
                "sector_type": "concept",
                "trade_date": sector_date,
                "pct_chg": 1.5,
                "amount": None,
                "net_amount": 80_000_000.0,
                "company_count": 1,
                "limit_up_count": None,
                "limit_up_count_status": "not_computed",
                "strong_count": None,
                "strong_count_status": "not_computed",
                "leader_code": None,
                "leader_name": None,
                "leader_pct_chg": None,
                "heat_score": 70.0,
                "source": "test",
                "updated_at": "2026-05-28T15:00:00",
            }
        ],
        ["sector_code", "sector_type", "trade_date"],
    )

    UpdateService(db)._update_market_sector_daily(sector_date, object(), [])
    row = DataService(db).sector_heatmap("concept")[0]

    assert row["member_count"] == 1
    assert row["limit_up_count"] is None
    assert row["limit_up_count_status"] == "missing_limit_data"
    assert row["strong_count"] is None
    assert row["strong_count_status"] == "missing_quote"
    assert row["limit_data_date"] is None
    assert row["quote_data_date"] is None


def test_update_checkpoints_and_dag_are_queryable(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    service._write_task("update-1", kind="update", status="running", stage="测试")

    service.record_checkpoint(
        "update-1",
        job_id="daily_basic",
        capability="每日指标",
        target_date=date(2026, 5, 22),
        batch_key="all",
        status="completed",
        rows_written=2,
        payload={"source": "Tushare daily_basic"},
    )
    data = DataService(db)

    checkpoints = data.task_checkpoints("update-1")
    dag = data.task_dag("update-1")

    assert checkpoints[0]["capability"] == "每日指标"
    assert checkpoints[0]["rows_written"] == 2
    assert any(node["id"] == "daily_basic" for node in dag["nodes"])
    assert {
        "stock_basic",
        "daily_snapshot",
        "history_qfq",
        "daily_basic",
        "stk_factor",
        "moneyflow",
        "limit_list_d",
        "cyq_perf",
        "cyq_chips",
        "ths_member",
        "board_moneyflow",
        "top_list",
        "top_inst",
        "hm_detail",
        "market_environment",
        "capability_refresh",
    }.issubset({node["id"] for node in dag["nodes"]})


def test_update_dag_marks_terminal_missing_nodes_and_blocked_dependents(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    service._write_task("update-running", kind="update", status="running", stage="测试")
    service._write_task("update-failed", kind="update", status="failed", stage="服务重启后中止")

    running_dag = DataService(db).task_dag("update-running")
    assert {node["status"] for node in running_dag["nodes"]} == {"queued"}

    failed_dag = DataService(db).task_dag("update-failed")
    assert failed_dag["nodes"][0]["status"] == "not_reached"

    service.record_checkpoint(
        "update-failed",
        job_id="history_qfq",
        capability="历史 K 线",
        target_date=date(2026, 5, 22),
        batch_key="all",
        status="failed",
        error_message="rate limit",
    )
    blocked_dag = DataService(db).task_dag("update-failed")
    status_by_id = {node["id"]: node["status"] for node in blocked_dag["nodes"]}
    assert status_by_id["history_qfq"] == "failed"
    assert status_by_id["daily_basic"] == "blocked"
    assert status_by_id["market_environment"] == "blocked"


def test_record_checkpoint_syncs_update_task_progress_to_dag(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    service._write_task("update-progress", kind="update", status="running", stage="测试", payload={})

    service.record_checkpoint(
        "update-progress",
        job_id="stock_basic",
        capability="股票基础信息",
        target_date=date(2026, 5, 22),
        batch_key="all",
        status="completed",
        rows_written=3,
    )
    service.record_checkpoint(
        "update-progress",
        job_id="daily_snapshot",
        capability="当天行情快照",
        target_date=date(2026, 5, 22),
        batch_key="all",
        status="skipped",
        payload={"reason": "coverage_complete"},
    )

    task = db.query("SELECT processed, total FROM task_runs WHERE id = ?", ["update-progress"])[0]

    assert task["total"] == len(DEFAULT_DATA_DAG)
    assert task["processed"] == 2


def test_market_environment_update_mode_uses_fast_path(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    service._write_task(
        "market-env",
        kind="update",
        status="running",
        stage="测试",
        payload={"mode": "market_environment"},
    )
    calls = []

    monkeypatch.setattr(service, "_target_history_date", lambda: date(2026, 5, 22))
    monkeypatch.setattr(service, "_update_market_environment", lambda target_date: calls.append(target_date) or 1)
    monkeypatch.setattr(service, "_update_basics", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("full update should not run")))
    monkeypatch.setattr(service.data_service, "refresh_capabilities", lambda: None)
    monkeypatch.setattr(service.data_service, "capabilities", lambda: [{"capability": "市场环境"}])

    service._run_update("market-env", {"mode": "market_environment"})

    task = db.query("SELECT status, stage, processed, total FROM task_runs WHERE id = ?", ["market-env"])[0]
    checkpoints = db.query("SELECT job_id, status FROM update_checkpoints WHERE task_id = ?", ["market-env"])

    assert calls == [date(2026, 5, 22)]
    assert task["status"] == "completed_full"
    assert task["stage"] == "市场环境已重算"
    assert task["total"] == len(DEFAULT_DATA_DAG)
    assert {row["job_id"]: row["status"] for row in checkpoints} == {
        "market_environment": "completed",
        "capability_refresh": "completed",
    }


def _import_routes_with_temp_db(tmp_path, monkeypatch):
    from backend.app import db as db_module
    import backend.app.api as api_package

    sys.modules.pop("backend.app.api.routes", None)
    if hasattr(api_package, "routes"):
        delattr(api_package, "routes")
    monkeypatch.setattr(db_module, "_database", Database(tmp_path / "routes_test.duckdb"), raising=False)
    from backend.app.api import routes

    return routes


def test_sync_today_route_maps_to_daily_light(tmp_path, monkeypatch):
    routes = _import_routes_with_temp_db(tmp_path, monkeypatch)

    calls = []

    class FakeUpdateService:
        def start_update(self, payload):
            calls.append(payload)
            return "update-test"

    monkeypatch.setattr(routes, "update_service", FakeUpdateService())
    client = TestClient(routes.router)

    response = client.post("/api/tasks/sync-today", json={})

    assert response.status_code == 200
    assert response.json()["task_id"] == "update-test"
    assert calls == [{"mode": "daily_light"}]


def test_backtest_lab_routes_enqueue_long_running_jobs(tmp_path, monkeypatch):
    routes = _import_routes_with_temp_db(tmp_path, monkeypatch)

    calls = []

    class FakeUpdateService:
        def start_signal_evaluation(self, payload, runner):
            calls.append(("signal", payload))
            return "task-signal", "signal-eval-test"

        def start_portfolio_backtest(self, payload, runner):
            calls.append(("portfolio", payload))
            return "task-portfolio", "portfolio-test"

    monkeypatch.setattr(routes, "update_service", FakeUpdateService())
    client = TestClient(routes.router)

    signal = client.post("/api/backtest/signal-evaluation", json={"config": {"candidate_limit": 3}})
    portfolio = client.post("/api/backtest/portfolio", json={"config": {"candidate_limit": 4}})

    assert signal.status_code == 200
    assert signal.json() == {"task_id": "task-signal", "run_id": "signal-eval-test", "status": "queued"}
    assert portfolio.status_code == 200
    assert portfolio.json() == {"task_id": "task-portfolio", "run_id": "portfolio-test", "status": "queued"}
    assert calls[0][0] == "signal"
    assert calls[1][0] == "portfolio"


def test_source_diagnostics_reports_tushare_configuration_and_fallbacks(tmp_path, monkeypatch):
    from backend.app import config as config_module

    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    now = datetime(2026, 5, 22, 10, 0)
    db.upsert(
        "source_status",
        [
            {
                "source": "Tushare 实时日线",
                "capability": "当天行情快照",
                "status": "failed",
                "last_checked": now,
                "last_success": None,
                "last_failure": now,
                "failure_reason": "Token 不对",
                "ttl_until": now,
                "payload_json": "{}",
            }
        ],
        ["source", "capability"],
    )
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行")], ["code"])
    db.upsert(
        "daily_snapshots",
        [
            {
                "code": "000001.SZ",
                "date": "2026-05-22",
                "name": "平安银行",
                "latest_price": 10.0,
                "pct_chg": 1.0,
                "high": 10.1,
                "low": 9.9,
                "volume": 1,
                "amount": 1,
                "turnover_rate": None,
                "float_market_value": None,
                "source": "AkShare 新浪",
                "updated_at": now,
            }
        ],
        ["code", "date"],
    )
    monkeypatch.setattr(
        config_module,
        "settings",
        type(
            "Settings",
            (),
            {
                "tushare_token": "token",
                "tushare_realtime_enabled": True,
                "tushare_history_enabled": True,
                "tushare_enrichment_enabled": True,
                "tushare_http_url": "http://101.35.233.113:8020/",
            },
        )(),
        raising=False,
    )

    result = DataService(db).source_diagnostics()

    assert result["tushare_token_configured"] is True
    assert result["tushare_http_url_configured"] is True
    assert result["last_tushare_error"] == "Token 不对"
    assert result["last_snapshot_source"] == "AkShare 新浪"
    assert result["realtime_status"] == "failed"


def test_intraday_boards_split_anomaly_pullback_and_risk(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = IntradayRadarService(db)
    trade_date = date(2026, 5, 22)
    db.upsert(
        "stock_basic",
        [_stock("000001.SZ", "异动"), _stock("000002.SZ", "低吸"), _stock("000003.SZ", "风险")],
        ["code"],
    )
    history = []
    for offset in range(25):
        day = trade_date - timedelta(days=25 - offset)
        history.append(_bar("000001.SZ", day, 10 + offset * 0.04, pct_chg=0.8, amount=10_000_000))
        history.append(_bar("000002.SZ", day, 12 + offset * 0.03, pct_chg=0.5, amount=12_000_000))
        history.append(_bar("000003.SZ", day, 8 + offset * 0.05, pct_chg=0.6, amount=9_000_000))
    db.upsert("historical_bars", history, ["code", "date"])
    first = datetime(2026, 5, 22, 9, 35)
    second = datetime(2026, 5, 22, 10, 5)
    service.record_snapshots(
        pd.DataFrame(
            [
                {"code": "000001.SZ", "name": "异动", "latest_price": 11.0, "pct_chg": 2.0, "high": 11.0, "low": 10.5, "amount": 12_000_000, "volume": 1_000_000},
                {"code": "000002.SZ", "name": "低吸", "latest_price": 12.3, "pct_chg": 0.6, "high": 12.8, "low": 12.1, "amount": 10_000_000, "volume": 900_000},
                {"code": "000003.SZ", "name": "风险", "latest_price": 9.0, "pct_chg": 6.0, "high": 9.4, "low": 8.9, "amount": 11_000_000, "volume": 1_100_000},
            ]
        ),
        sample_at=first,
        trade_date=trade_date,
    )
    service.record_snapshots(
        pd.DataFrame(
            [
                {"code": "000001.SZ", "name": "异动", "latest_price": 11.6, "pct_chg": 5.5, "high": 11.7, "low": 10.8, "amount": 80_000_000, "volume": 5_000_000},
                {"code": "000002.SZ", "name": "低吸", "latest_price": 12.4, "pct_chg": 0.9, "high": 12.9, "low": 12.2, "amount": 30_000_000, "volume": 2_000_000},
                {"code": "000003.SZ", "name": "风险", "latest_price": 8.95, "pct_chg": 1.0, "high": 9.7, "low": 8.8, "amount": 90_000_000, "volume": 6_000_000},
            ]
        ),
        sample_at=second,
        trade_date=trade_date,
    )

    boards = service.boards(sample_at=second, limit=10)

    assert boards["anomaly"][0]["code"] == "000001.SZ"
    assert any(row["code"] == "000002.SZ" for row in boards["pullback"])
    assert boards["risk"][0]["code"] == "000003.SZ"
    assert boards["theme_pulse"] == []


def test_watchlist_records_hypothesis_fields(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行")], ["code"])
    service = WatchlistService(db)

    created = service.add_items(
        {
            "source_type": "strategy",
            "source_label": "Scanner",
            "batch_date": "2026-05-22",
            "items": [
                {
                    "code": "000001.SZ",
                    "name": "平安银行",
                    "entry_price": 10.0,
                    "hypothesis": "题材放量突破",
                    "invalidation_rule": "跌破平台上沿",
                    "trigger_rules": ["RPS20 ≥ 70", "量比 ≥ 1.5"],
                    "tags": ["半导体", "突破"],
                }
            ],
        }
    )

    item = WatchlistService(db).result()["batches"][0]["items"][0]

    assert created["added"] == 1
    assert item["hypothesis"] == "题材放量突破"
    assert item["invalidation_rule"] == "跌破平台上沿"
    assert item["trigger_rules"] == ["RPS20 ≥ 70", "量比 ≥ 1.5"]
    assert item["tags"] == ["半导体", "突破"]


def test_signal_evaluation_and_portfolio_backtest_contracts(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ", "平安银行"), _stock("600000.SH", "浦发银行")], ["code"])
    start = date(2026, 1, 1)
    bars = []
    for offset in range(90):
        day = start + timedelta(days=offset)
        bars.append(_bar("000001.SZ", day, 10 + offset * 0.08, pct_chg=1.0, amount=80_000_000))
        bars.append(_bar("600000.SH", day, 10 - offset * 0.01, pct_chg=-0.2, amount=70_000_000))
    db.upsert("historical_bars", bars, ["code", "date"])
    service = BacktestService(db)

    evaluation = service.run_signal_evaluation(
        {
            "start_date": "2026-02-01",
            "end_date": "2026-02-20",
            "step": 5,
            "candidate_limit": 5,
            "config": {"min_price": 1, "min_amount": 1, "candidate_limit": 5},
        }
    )
    portfolio = service.run_portfolio_backtest(
        {
            "start_date": "2026-02-01",
            "end_date": "2026-02-20",
            "max_positions": 2,
            "hold_days": 5,
            "transaction_cost_bps": 5,
            "slippage_bps": 5,
            "config": {"min_price": 1, "min_amount": 1, "candidate_limit": 5},
        }
    )

    assert evaluation["run"]["id"].startswith("signal-eval-")
    assert "rank_ic" in evaluation["run"]["summary"]
    assert portfolio["run"]["id"].startswith("portfolio-")
    assert portfolio["run"]["summary"]["trade_count"] >= 0
    assert "equity_curve" in portfolio
