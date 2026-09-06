from contextlib import contextmanager
from datetime import date, datetime

import pandas as pd

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services import update_service as update_module
from backend.app.services.update_service import UpdateService


def _stock(code: str, suspended: bool = False) -> dict:
    return {
        "code": code,
        "name": code,
        "exchange": code.split(".")[-1],
        "list_date": "2020-01-01",
        "source": "test",
        "is_st": False,
        "suspended": suspended,
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

    assert [row["code"] for row in rows] == ["000001.SZ", "000003.SZ", "300750.SZ", "600000.SH"]


def test_history_update_stock_picker_excludes_inactive_stocks_in_full_and_light_modes(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "stock_basic",
        [_stock("000001.SZ"), _stock("000003.SZ", suspended=True)],
        ["code"],
    )
    db.upsert(
        "daily_snapshots",
        [_snapshot("000001.SZ"), _snapshot("000003.SZ")],
        ["code", "date"],
    )
    db.upsert(
        "historical_bars",
        [_bar("000003.SZ", "2026-05-10")],
        ["code", "date"],
    )

    service = UpdateService(db)
    full_rows = service._history_stocks_for_update(limit=0, light=False, target_history_date=date(2026, 5, 20))
    light_rows = service._history_stocks_for_update(limit=0, light=True, target_history_date=date(2026, 5, 20))

    assert [row["code"] for row in full_rows] == ["000001.SZ"]
    assert [row["code"] for row in light_rows] == ["000001.SZ"]


def test_target_history_date_uses_previous_trading_day_before_china_close(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    assert service._target_history_date(datetime(2026, 5, 21, 8, 30)) == date(2026, 5, 20)
    assert service._target_history_date(datetime(2026, 5, 21, 16, 30)) == date(2026, 5, 21)
    assert service._target_history_date(datetime(2026, 5, 23, 10, 0)) == date(2026, 5, 22)


def test_incremental_history_refreshes_the_adjusted_analysis_window(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    assert service._history_fetch_start(date(2026, 1, 1), "2026-05-18", incremental=True) == date(2026, 1, 1)
    assert service._history_fetch_start(date(2026, 1, 1), None, incremental=True) == date(2026, 1, 1)


def test_baostock_history_reuses_one_session_and_refreshes_qfq_window(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    calls = []
    session_client = object()

    class FakeBaostock:
        @contextmanager
        def session(self):
            calls.append("login")
            try:
                yield session_client
            finally:
                calls.append("logout")

        def fetch_history(self, code, start_date, end_date, client=None):
            calls.append((code, start_date, end_date, client))
            return pd.DataFrame([_bar(code, end_date.isoformat())])

    service = UpdateService(db)
    monkeypatch.setattr(service.baostock_guard, "sleep", lambda: None)
    result = service._update_history(
        [
            {"code": "000001.SZ", "latest_history_date": "2026-05-21"},
            {"code": "600000.SH", "latest_history_date": "2026-05-20"},
        ],
        date(2026, 1, 1),
        date(2026, 5, 22),
        force=False,
        task_id="missing-task",
        incremental=True,
        target_history_date=date(2026, 5, 22),
        source=FakeBaostock(),
    )

    history_calls = [item for item in calls if isinstance(item, tuple)]
    assert result == (2, 0, 0)
    assert calls[0] == "login"
    assert calls[-1] == "logout"
    assert len(history_calls) == 2
    assert history_calls[0][1] == date(2026, 1, 1)
    assert history_calls[1][1] == date(2026, 1, 1)
    assert all(item[3] is session_client for item in history_calls)


def test_baostock_history_stops_after_consecutive_failures(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    calls = []

    class FailingBaostock:
        @contextmanager
        def session(self):
            yield self

        def fetch_history(self, code, start_date, end_date, client=None):
            calls.append(code)
            raise TimeoutError("socket timed out")

    service = UpdateService(db)
    monkeypatch.setattr(service.baostock_guard, "sleep", lambda: None)
    monkeypatch.setattr(
        update_module,
        "settings",
        type("Settings", (), {"baostock_max_consecutive_failures": 2})(),
    )

    try:
        service._update_history(
            [{"code": "000001.SZ"}, {"code": "000002.SZ"}, {"code": "000003.SZ"}],
            date(2026, 5, 1),
            date(2026, 5, 22),
            force=False,
            task_id="missing-task",
            source=FailingBaostock(),
        )
    except update_module.SourceUnavailable as exc:
        assert "连续 2 只股票请求失败" in str(exc)
    else:
        raise AssertionError("expected the Baostock circuit breaker to abort the update")

    assert calls == ["000001.SZ", "000002.SZ"]
