from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services import update_service as update_module
from backend.app.services.data_service import DataService
from backend.app.services.update_service import UpdateService
from backend.app.sources.base import SourceFetchResult


def _stock(code: str = "000001.SZ", source: str = "Baostock") -> dict:
    return {
        "code": code,
        "name": "平安银行",
        "exchange": code.split(".")[-1],
        "list_date": "1991-04-03",
        "source": source,
        "is_st": False,
        "suspended": False,
        "updated_at": "2026-05-21T10:00:00",
    }


def _snapshot_frame(source: str = "AkShare 新浪") -> pd.DataFrame:
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
                "source": source,
                "freshness": "realtime",
            }
        ]
    )


def test_probe_sources_uses_baostock_and_sina_in_free_mode(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)

    class FakeBaostockSource:
        def fetch_stock_basics(self, include_bj=False, exclude_star=False):
            return pd.DataFrame([_stock()])

    class FakeAkShareSource:
        def fetch_sina_snapshot(self, include_bj=False, exclude_star=False):
            return _snapshot_frame()

    monkeypatch.setattr(update_module, "BaostockSource", FakeBaostockSource)
    monkeypatch.setattr(update_module, "AkShareSource", FakeAkShareSource)
    service = UpdateService(db)
    monkeypatch.setattr(service.public_guard, "sleep", lambda: None)
    monkeypatch.setattr(service.baostock_guard, "sleep", lambda: None)

    rows = service.probe_sources({"include_bj": False, "exclude_star_board": False})

    assert {row["source"] for row in rows} == {"Baostock", "AkShare 新浪"}
    assert all(row["status"] == "available" for row in rows)


def test_source_diagnostics_keep_free_sources_and_hide_retired_sources(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    now = datetime(2026, 5, 21, 10, 0)
    db.upsert(
        "source_status",
        [
            {
                "source": "AkShare 新浪",
                "capability": "当天行情快照",
                "status": "available",
                "last_checked": now,
                "last_success": now,
                "last_failure": None,
                "failure_reason": None,
                "ttl_until": now,
                "payload_json": {"rows": 1},
            },
            {
                "source": "Baostock",
                "capability": "历史 K 线",
                "status": "available",
                "last_checked": now,
                "last_success": now,
                "last_failure": None,
                "failure_reason": None,
                "ttl_until": now,
                "payload_json": {"rows": 1},
            },
            {
                "source": "AData",
                "capability": "当天行情快照",
                "status": "failed",
                "last_checked": now,
                "last_success": None,
                "last_failure": now,
                "failure_reason": "retired",
                "ttl_until": now,
                "payload_json": {},
            },
        ],
        ["source", "capability"],
    )

    diagnostics = DataService(db).source_diagnostics()
    returned_sources = {row["source"] for row in diagnostics["rows"]}

    assert diagnostics["mode"] == "free"
    assert returned_sources == {"AkShare 新浪", "Baostock"}


def test_intraday_snapshot_falls_back_to_sina_when_optional_tushare_fails(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)

    class FailingTushareSource:
        def fetch_realtime_daily(self, *args, **kwargs):
            raise RuntimeError("Tushare unavailable")

    monkeypatch.setattr(update_module, "_tushare_realtime_configured", lambda: True)
    monkeypatch.setattr(update_module, "TushareRealtimeSource", FailingTushareSource)
    service = UpdateService(db)
    monkeypatch.setattr(
        service,
        "_fetch_sina_snapshot",
        lambda *args, **kwargs: SourceFetchResult(
            source="AkShare 新浪",
            capability="盘中行情快照",
            status="available",
            frame=_snapshot_frame(),
        ),
    )
    warnings = []

    frame = service._fetch_intraday_snapshot_frame(False, False, warnings)

    assert frame.iloc[0]["source"] == "AkShare 新浪"
    assert any("回退新浪" in warning for warning in warnings)


def test_daily_snapshot_falls_back_to_sina_when_optional_tushare_fails(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)

    class FailingTushareSource:
        def fetch_realtime_daily(self, *args, **kwargs):
            raise RuntimeError("Tushare unavailable")

    monkeypatch.setattr(update_module, "_tushare_realtime_configured", lambda: True)
    monkeypatch.setattr(update_module, "TushareRealtimeSource", FailingTushareSource)
    service = UpdateService(db)
    monkeypatch.setattr(
        service,
        "_fetch_sina_snapshot",
        lambda *args, **kwargs: SourceFetchResult(
            source="AkShare 新浪",
            capability="当天行情快照",
            status="available",
            frame=_snapshot_frame(),
        ),
    )

    count = service._update_snapshots(True, False, False, warnings=[])

    assert count == 1
    assert db.scalar("SELECT source FROM daily_snapshots LIMIT 1") == "AkShare 新浪"


def test_stock_basics_use_baostock_in_free_mode(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)

    class FakeBaostockSource:
        def fetch_stock_basics(self, *args, **kwargs):
            return pd.DataFrame([_stock()])

    service = UpdateService(db)
    count = service._update_basics(True, False, False, warnings=[], source=FakeBaostockSource())

    assert count == 1
    assert db.scalar("SELECT source FROM stock_basic LIMIT 1") == "Baostock"


def test_history_update_uses_baostock_when_tushare_is_disabled(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)

    class FakeBaostockSource:
        @contextmanager
        def session(self):
            yield self

        def fetch_history(self, code, start_date, end_date, client=None):
            return pd.DataFrame(
                [
                    {
                        "code": code,
                        "date": end_date,
                        "open": 10.0,
                        "high": 10.5,
                        "low": 9.8,
                        "close": 10.2,
                        "prev_close": 10.0,
                        "volume": 1000.0,
                        "amount": 10_200.0,
                        "turn": 2.0,
                        "pct_chg": 2.0,
                        "tradestatus": "1",
                        "is_st": False,
                        "source": "Baostock",
                        "updated_at": datetime(2026, 5, 21, 16, 0),
                    }
                ]
            )

    monkeypatch.setattr(update_module, "_tushare_history_configured", lambda: False)
    service = UpdateService(db)
    monkeypatch.setattr(service.baostock_guard, "sleep", lambda: None)

    result = service._update_history(
        [{"code": "000001.SZ"}],
        date(2026, 1, 1),
        date(2026, 5, 21),
        force=True,
        task_id="missing-task",
        source=FakeBaostockSource(),
    )

    assert result == (1, 0, 0)
    assert db.scalar("SELECT source FROM historical_bars LIMIT 1") == "Baostock"


def test_requirements_include_pinned_free_source_dependencies():
    requirements = Path(__file__).resolve().parents[2].joinpath("requirements.txt").read_text()

    assert "akshare==" in requirements.lower()
    assert "baostock==" in requirements.lower()
