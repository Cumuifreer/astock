from datetime import date

from backend.app.db import Database
from backend.app.schema import migrate
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


def test_light_daily_update_selects_only_stale_or_missing_history(tmp_path):
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
        today=date(2026, 5, 20),
    )

    assert [row["code"] for row in rows] == ["300750.SZ", "600000.SH"]


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
