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
        def fetch_history_reference_factors(self, end, codes=None):
            assert end == date(2026, 5, 22)
            assert codes == ["000001.SZ", "600000.SH"]
            return {"000001.SZ": 2.0, "600000.SH": 1.0}, "2026-05-22"

        def fetch_history_day(self, day, reference_factors, codes=None, progress=None):
            if day != date(2026, 5, 22):
                return pd.DataFrame()
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


def test_tushare_history_streams_each_day_to_db_and_task_heartbeat(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ"), _stock("600000.SH")], ["code"])
    service = UpdateService(db)
    service._write_task("task-stream", kind="update", status="running", stage="轻量补齐历史 K 线")

    class FakeStreamingTushareSource:
        def fetch_history_reference_factors(self, end, codes=None):
            assert end == date(2026, 5, 22)
            assert codes == ["000001.SZ", "600000.SH"]
            return {"000001.SZ": 2.0, "600000.SH": 1.0}, "2026-05-22"

        def fetch_history_day(self, day, reference_factors, codes=None, progress=None):
            assert reference_factors == {"000001.SZ": 2.0, "600000.SH": 1.0}
            assert codes == ["000001.SZ", "600000.SH"]
            if progress:
                progress("daily")
                progress("adj_factor")
                progress("daily_basic")
            return pd.DataFrame(
                [
                    {
                        "code": "000001.SZ",
                        "date": day.isoformat(),
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
                    }
                ]
            )

    monkeypatch.setattr(update_module, "TushareEnrichmentSource", FakeStreamingTushareSource)

    success, failed, skipped = service._update_tushare_history(
        [{"code": "000001.SZ"}, {"code": "600000.SH"}],
        date(2026, 5, 21),
        date(2026, 5, 22),
        "task-stream",
    )

    rows = db.query("SELECT code, date FROM historical_bars ORDER BY date, code")
    task = db.query("SELECT * FROM task_runs WHERE id = 'task-stream'")[0]
    summary = update_module.json.loads(task["summary_json"])
    progress = summary["history_progress"]
    assert (success, failed, skipped) == (1, 0, 1)
    assert [row["date"].isoformat() for row in rows] == ["2026-05-21", "2026-05-22"]
    assert task["processed"] == 2
    assert task["total"] == 2
    assert progress["mode"] == "streaming"
    assert progress["current_date"] == "2026-05-22"
    assert progress["step"] == "完成"
    assert progress["written_rows"] == 2
    assert progress["reference_date"] == "2026-05-22"


def test_tushare_history_stream_keeps_written_days_when_later_day_fails(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ")], ["code"])
    service = UpdateService(db)
    service._write_task("task-fail", kind="update", status="running", stage="轻量补齐历史 K 线")

    class PartlyFailingTushareSource:
        def fetch_history_reference_factors(self, end, codes=None):
            return {"000001.SZ": 2.0}, "2026-05-22"

        def fetch_history_day(self, day, reference_factors, codes=None, progress=None):
            if day == date(2026, 5, 22):
                raise RuntimeError("Tushare timeout")
            return pd.DataFrame(
                [
                    {
                        "code": "000001.SZ",
                        "date": day.isoformat(),
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
                        "updated_at": "2026-05-21T18:30:00",
                    }
                ]
            )

    monkeypatch.setattr(update_module, "TushareEnrichmentSource", PartlyFailingTushareSource)

    try:
        service._update_tushare_history(
            [{"code": "000001.SZ"}],
            date(2026, 5, 21),
            date(2026, 5, 22),
            "task-fail",
        )
    except RuntimeError:
        pass

    rows = db.query("SELECT code, date FROM historical_bars")
    assert [(row["code"], row["date"].isoformat()) for row in rows] == [("000001.SZ", "2026-05-21")]


def test_tushare_history_counts_latest_weekday_when_end_is_weekend(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ")], ["code"])
    service = UpdateService(db)
    service._write_task("task-weekend", kind="update", status="running", stage="轻量补齐历史 K 线")

    class WeekendTushareSource:
        def fetch_history_reference_factors(self, end, codes=None):
            assert end == date(2026, 5, 24)
            return {"000001.SZ": 2.0}, "2026-05-22"

        def fetch_history_day(self, day, reference_factors, codes=None, progress=None):
            assert day == date(2026, 5, 22)
            return pd.DataFrame(
                [
                    {
                        "code": "000001.SZ",
                        "date": day.isoformat(),
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
                    }
                ]
            )

    monkeypatch.setattr(update_module, "TushareEnrichmentSource", WeekendTushareSource)

    success, failed, skipped = service._update_tushare_history(
        [{"code": "000001.SZ"}],
        date(2026, 5, 22),
        date(2026, 5, 24),
        "task-weekend",
    )

    task = db.query("SELECT * FROM task_runs WHERE id = 'task-weekend'")[0]
    summary = update_module.json.loads(task["summary_json"])
    assert (success, failed, skipped) == (1, 0, 0)
    assert summary["history_progress"]["current_date"] == "2026-05-22"
