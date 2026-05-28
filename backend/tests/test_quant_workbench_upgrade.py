import json
from datetime import date, datetime, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.backtest_service import BacktestService
from backend.app.services.data_service import DataService
from backend.app.services.intraday_service import IntradayRadarService
from backend.app.services.update_service import UpdateService
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
    assert overview["sector_heatmap"][0]["name"] == "半导体设备"
    assert overview["action_items"]
    assert heatmap[0]["heat_score"] == 86.5


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


def test_sync_today_route_maps_to_daily_light(monkeypatch):
    from backend.app.api import routes

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
