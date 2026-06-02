from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.data_service import DataService
from backend.app.services import update_service as update_module
from backend.app.services.update_service import UpdateService


FORBIDDEN_SOURCES = ("AkShare", "Baostock", "AData")


def _stock(code: str = "000001.SZ") -> dict:
    return {
        "code": code,
        "name": "平安银行",
        "exchange": code.split(".")[-1],
        "list_date": "1991-04-03",
        "source": "Tushare stock_basic",
        "is_st": False,
        "suspended": False,
        "updated_at": "2026-05-21T10:00:00",
    }


def _snapshot_frame() -> pd.DataFrame:
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


def _install_forbidden_legacy_sources(monkeypatch) -> dict:
    calls = {"akshare": 0, "baostock": 0}

    class ForbiddenAkShareSource:
        def fetch_sina_snapshot(self, *_args, **_kwargs):
            calls["akshare"] += 1
            raise AssertionError("AkShare should not be called in Tushare-only mode")

        def fetch_tencent_snapshot(self, *_args, **_kwargs):
            calls["akshare"] += 1
            raise AssertionError("AkShare should not be called in Tushare-only mode")

    class ForbiddenBaostockSource:
        def fetch_stock_basics(self, *_args, **_kwargs):
            calls["baostock"] += 1
            raise AssertionError("Baostock should not be called in Tushare-only mode")

        def fetch_history(self, *_args, **_kwargs):
            calls["baostock"] += 1
            raise AssertionError("Baostock should not be called in Tushare-only mode")

    monkeypatch.setattr(update_module, "AkShareSource", ForbiddenAkShareSource, raising=False)
    monkeypatch.setattr(update_module, "BaostockSource", ForbiddenBaostockSource, raising=False)
    return calls


def test_probe_sources_returns_tushare_only_and_does_not_call_legacy_sources(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    calls = _install_forbidden_legacy_sources(monkeypatch)

    class FakeTushareRealtimeSource:
        def fetch_realtime_daily(self, include_bj=False, exclude_star=False):
            return _snapshot_frame()

    class FakeTushareEnrichmentSource:
        def fetch_stock_basics(self, include_bj=False, exclude_star=False):
            return pd.DataFrame([_stock()])

    monkeypatch.setattr(update_module, "_tushare_realtime_configured", lambda: True)
    monkeypatch.setattr(update_module, "TushareRealtimeSource", FakeTushareRealtimeSource)
    monkeypatch.setattr(update_module, "TushareEnrichmentSource", FakeTushareEnrichmentSource)

    rows = UpdateService(db).probe_sources({"include_bj": False, "exclude_star_board": False})

    assert calls == {"akshare": 0, "baostock": 0}
    assert rows
    assert {row["capability"] for row in rows} == {"股票基础信息", "当天行情快照"}
    assert all(row["source"].startswith("Tushare") for row in rows)
    assert all(not any(name in row["source"] for name in FORBIDDEN_SOURCES) for row in rows)


def test_source_diagnostics_and_capabilities_hide_legacy_external_sources(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock()], ["code"])
    now = datetime(2026, 5, 21, 10, 0)
    db.upsert(
        "source_status",
        [
            {
                "source": "AkShare 新浪",
                "capability": "当天行情快照",
                "status": "failed",
                "last_checked": now,
                "last_success": None,
                "last_failure": now,
                "failure_reason": "legacy source",
                "ttl_until": now,
                "payload_json": {},
            },
            {
                "source": "Baostock",
                "capability": "历史 K 线",
                "status": "failed",
                "last_checked": now,
                "last_success": None,
                "last_failure": now,
                "failure_reason": "legacy source",
                "ttl_until": now,
                "payload_json": {},
            },
            {
                "source": "AData",
                "capability": "当天行情快照",
                "status": "available",
                "last_checked": now,
                "last_success": now,
                "last_failure": None,
                "failure_reason": None,
                "ttl_until": now,
                "payload_json": {},
            },
            {
                "source": "Tushare 实时日线",
                "capability": "当天行情快照",
                "status": "available",
                "last_checked": now,
                "last_success": now,
                "last_failure": None,
                "failure_reason": None,
                "ttl_until": now,
                "payload_json": {"rows": 1},
            },
        ],
        ["source", "capability"],
    )

    service = DataService(db)
    diagnostics = service.source_diagnostics()
    capabilities = service.capabilities()

    returned_sources = " ".join(row["source"] for row in diagnostics["rows"])
    fallback_sources = " ".join(source for row in capabilities for source in row["fallback_sources"])
    for forbidden in FORBIDDEN_SOURCES:
        assert forbidden not in returned_sources
        assert forbidden not in fallback_sources


def test_intraday_snapshot_does_not_fallback_to_akshare_when_tushare_fails(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    calls = _install_forbidden_legacy_sources(monkeypatch)

    class FailingTushareSource:
        def fetch_realtime_daily(self, include_bj=False, exclude_star=False):
            raise RuntimeError("Tushare unavailable")

    monkeypatch.setattr(update_module, "_tushare_realtime_configured", lambda: True)
    monkeypatch.setattr(update_module, "TushareRealtimeSource", FailingTushareSource)

    with pytest.raises(RuntimeError, match="Tushare"):
        UpdateService(db)._fetch_intraday_snapshot_frame(False, False, warnings=[])

    assert calls == {"akshare": 0, "baostock": 0}


def test_daily_snapshot_does_not_fallback_to_akshare_when_tushare_fails(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    calls = _install_forbidden_legacy_sources(monkeypatch)

    class FailingTushareSource:
        def fetch_realtime_daily(self, include_bj=False, exclude_star=False):
            raise RuntimeError("Tushare unavailable")

    monkeypatch.setattr(update_module, "_tushare_realtime_configured", lambda: True)
    monkeypatch.setattr(update_module, "TushareRealtimeSource", FailingTushareSource)

    with pytest.raises(RuntimeError, match="Tushare"):
        UpdateService(db)._update_snapshots(True, False, False, warnings=[])

    assert calls == {"akshare": 0, "baostock": 0}


def test_daily_snapshot_defaults_missing_source_to_tushare_label(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    frame = _snapshot_frame().drop(columns=["source"])

    count = UpdateService(db)._upsert_realtime_daily_snapshots(frame, date(2026, 5, 21))

    row = db.query("SELECT source FROM daily_snapshots WHERE code = '000001.SZ'")[0]
    assert count == 1
    assert row["source"] == "Tushare 实时日线"


def test_stock_basics_use_tushare_without_baostock_or_akshare(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    calls = _install_forbidden_legacy_sources(monkeypatch)

    class FakeTushareEnrichmentSource:
        def fetch_stock_basics(self, include_bj=False, exclude_star=False):
            return pd.DataFrame([_stock()])

    monkeypatch.setattr(update_module, "TushareEnrichmentSource", FakeTushareEnrichmentSource)

    count = UpdateService(db)._update_basics(True, False, False, warnings=[])

    rows = db.query("SELECT code, source FROM stock_basic")
    assert calls == {"akshare": 0, "baostock": 0}
    assert count == 1
    assert rows == [{"code": "000001.SZ", "source": "Tushare stock_basic"}]


def test_history_update_does_not_fallback_to_baostock_when_tushare_fails(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock()], ["code"])
    calls = _install_forbidden_legacy_sources(monkeypatch)

    class FailingTushareHistorySource:
        def fetch_history_reference_factors(self, end, codes=None):
            raise RuntimeError("Tushare history unavailable")

    monkeypatch.setattr(update_module, "_tushare_history_configured", lambda: True)
    monkeypatch.setattr(update_module, "TushareEnrichmentSource", FailingTushareHistorySource)

    with pytest.raises(RuntimeError, match="Tushare"):
        UpdateService(db)._update_history(
            [{"code": "000001.SZ"}],
            date(2026, 1, 1),
            date(2026, 5, 21),
            force=True,
            task_id="missing-task",
        )

    assert calls == {"akshare": 0, "baostock": 0}


def test_requirements_do_not_include_akshare_or_baostock_runtime_dependencies():
    requirements = Path(__file__).resolve().parents[2].joinpath("requirements.txt").read_text()

    assert "akshare" not in requirements.lower()
    assert "baostock" not in requirements.lower()
