from datetime import date, datetime

import pandas as pd

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services import update_service as update_module
from backend.app.services.update_service import UpdateService


def _stock(code: str) -> dict:
    return {
        "code": code,
        "name": code,
        "exchange": code.split(".")[-1],
        "list_date": "2020-01-01",
        "source": "test",
        "is_st": False,
        "suspended": False,
        "updated_at": "2026-05-20T10:00:00",
    }


def _bar(code: str, day: str) -> dict:
    return {
        "code": code,
        "date": day,
        "open": 10.0,
        "high": 10.5,
        "low": 9.8,
        "close": 10.1,
        "prev_close": 10.0,
        "volume": 1000.0,
        "amount": 10_100.0,
        "turn": 2.0,
        "pct_chg": 1.0,
        "tradestatus": "1",
        "is_st": False,
        "source": "Baostock",
        "updated_at": "2026-05-20T15:00:00",
    }


def _snapshot(code: str) -> dict:
    return {
        "code": code,
        "date": "2026-05-20",
        "name": code,
        "latest_price": 10.0,
        "pct_chg": 1.0,
        "high": 10.5,
        "low": 9.8,
        "volume": 1000.0,
        "amount": 10_000.0,
        "turnover_rate": 2.0,
        "float_market_value": None,
        "source": "AkShare 新浪",
        "updated_at": "2026-05-20T10:00:00",
    }


def test_light_daily_update_selects_stocks_behind_target_history_date(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "stock_basic",
        [_stock("000001.SZ"), _stock("600000.SH"), _stock("300750.SZ"), _stock("000003.SZ")],
        ["code"],
    )
    db.upsert(
        "daily_snapshots",
        [_snapshot("000001.SZ"), _snapshot("600000.SH"), _snapshot("300750.SZ")],
        ["code", "date"],
    )
    db.upsert(
        "historical_bars",
        [
            _bar("000001.SZ", "2026-05-18"),
            _bar("600000.SH", "2026-05-10"),
            _bar("000003.SZ", "2026-05-10"),
        ],
        ["code", "date"],
    )

    rows = UpdateService(db)._history_stocks_for_update(
        limit=0,
        light=True,
        target_history_date=date(2026, 5, 20),
    )

    assert [row["code"] for row in rows] == ["000001.SZ", "300750.SZ", "600000.SH"]


def test_target_history_date_uses_previous_trading_day_before_china_close(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    assert service._target_history_date(datetime(2026, 5, 21, 8, 30)) == date(2026, 5, 20)
    assert service._target_history_date(datetime(2026, 5, 21, 16, 30)) == date(2026, 5, 21)
    assert service._target_history_date(datetime(2026, 5, 23, 10, 0)) == date(2026, 5, 22)


def test_incremental_history_start_continues_after_latest_bar(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    assert service._history_fetch_start(date(2026, 1, 1), "2026-05-18", incremental=True) == date(
        2026,
        5,
        19,
    )
    assert service._history_fetch_start(date(2026, 1, 1), None, incremental=True) == date(2026, 1, 1)


def test_history_update_prefers_tushare_batch_and_refreshes_qfq_window(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ"), _stock("600000.SH")], ["code"])

    class FakeTushareHistorySource:
        def fetch_history_bars(self, start, end, codes=None):
            assert start == date(2026, 1, 1)
            assert end == date(2026, 5, 22)
            assert codes == ["000001.SZ", "600000.SH"]
            return pd.DataFrame(
                [
                    {
                        "code": "000001.SZ",
                        "date": "2026-05-22",
                        "open": 5.0,
                        "high": 6.0,
                        "low": 4.5,
                        "close": 5.5,
                        "prev_close": 4.5,
                        "volume": 100_000.0,
                        "amount": 1_200_000.0,
                        "turn": 2.5,
                        "pct_chg": 22.22,
                        "tradestatus": "1",
                        "is_st": None,
                        "source": "Tushare daily 前复权",
                        "updated_at": "2026-05-22T18:30:00",
                    },
                    {
                        "code": "600000.SH",
                        "date": "2026-05-22",
                        "open": 10.0,
                        "high": 10.8,
                        "low": 9.8,
                        "close": 10.6,
                        "prev_close": 10.0,
                        "volume": 80_000.0,
                        "amount": 900_000.0,
                        "turn": 1.2,
                        "pct_chg": 6.0,
                        "tradestatus": "1",
                        "is_st": None,
                        "source": "Tushare daily 前复权",
                        "updated_at": "2026-05-22T18:30:00",
                    },
                ]
            )

    class FailingBaostockSource:
        def fetch_history(self, *_args, **_kwargs):
            raise AssertionError("Baostock should not be used when Tushare history is available")

    monkeypatch.setattr(update_module, "_tushare_history_configured", lambda: True, raising=False)
    monkeypatch.setattr(update_module, "TushareEnrichmentSource", FakeTushareHistorySource)
    monkeypatch.setattr(update_module, "BaostockSource", FailingBaostockSource)

    success, failed, skipped = UpdateService(db)._update_history(
        [{"code": "000001.SZ", "latest_history_date": "2026-05-21"}, {"code": "600000.SH"}],
        date(2026, 1, 1),
        date(2026, 5, 22),
        force=False,
        task_id="missing-task",
        incremental=True,
        target_history_date=date(2026, 5, 22),
    )

    rows = db.query("SELECT code, open, source FROM historical_bars ORDER BY code")
    assert (success, failed, skipped) == (2, 0, 0)
    assert [row["code"] for row in rows] == ["000001.SZ", "600000.SH"]
    assert rows[0]["open"] == 5.0
    assert rows[0]["source"] == "Tushare daily 前复权"
