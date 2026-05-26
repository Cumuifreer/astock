from datetime import date

import pandas as pd

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.data_service import DataService
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


class FakeTushareEnrichmentSource:
    def fetch_daily_basic(self, trade_date):
        assert trade_date == date(2026, 5, 22)
        return pd.DataFrame(
            [
                {
                    "code": "000001.SZ",
                    "trade_date": "2026-05-22",
                    "close": 12.3,
                    "turnover_rate": 2.5,
                    "volume_ratio": 1.8,
                    "float_share": 1_000_000.0,
                    "circ_mv": 12_300_000.0,
                    "source": "Tushare daily_basic",
                    "updated_at": "2026-05-22T18:30:00",
                }
            ]
        )


class FakeFullTushareEnrichmentSource(FakeTushareEnrichmentSource):
    def fetch_stk_factor(self, trade_date):
        return pd.DataFrame(
            [
                {
                    "code": "000001.SZ",
                    "trade_date": "2026-05-22",
                    "macd": 0.1,
                    "source": "Tushare stk_factor",
                    "updated_at": "2026-05-22T18:30:00",
                }
            ]
        )

    def fetch_moneyflow(self, trade_date):
        return pd.DataFrame(
            [
                {
                    "code": "000001.SZ",
                    "trade_date": "2026-05-22",
                    "net_mf_amount": 10000.0,
                    "main_net_amount": 20000.0,
                    "source": "Tushare moneyflow",
                    "updated_at": "2026-05-22T18:30:00",
                }
            ]
        )

    def fetch_limit_list_d(self, trade_date):
        return pd.DataFrame(
            [
                {
                    "code": "000001.SZ",
                    "trade_date": "2026-05-22",
                    "name": "平安银行",
                    "limit": "U",
                    "open_times": 1,
                    "source": "Tushare limit_list_d",
                    "updated_at": "2026-05-22T18:30:00",
                }
            ]
        )

    def fetch_cyq_perf_for_codes(self, codes, trade_date, limit=0):
        return pd.DataFrame(
            [
                {
                    "code": codes[0],
                    "trade_date": "2026-05-22",
                    "winner_rate": 0.61,
                    "cost_50pct": 11.8,
                    "source": "Tushare cyq_perf",
                    "updated_at": "2026-05-22T18:30:00",
                }
            ]
        )

    def fetch_cyq_chips_for_codes(self, codes, trade_date, limit=0):
        return pd.DataFrame(
            [
                {
                    "code": codes[0],
                    "trade_date": "2026-05-22",
                    "price": 12.0,
                    "percent": 0.03,
                    "source": "Tushare cyq_chips",
                    "updated_at": "2026-05-22T18:30:00",
                }
            ]
        )

    def fetch_ths_member_for_codes(self, codes, limit=0):
        return pd.DataFrame(
            [
                {
                    "code": codes[0],
                    "name": "平安银行",
                    "con_code": "885800.TI",
                    "con_name": "消费电子",
                    "source": "Tushare ths_member",
                    "updated_at": "2026-05-22T18:30:00",
                }
            ]
        )

    def fetch_top_list(self, trade_date):
        return pd.DataFrame(
            [
                {
                    "code": "000001.SZ",
                    "trade_date": "2026-05-22",
                    "name": "平安银行",
                    "net_amount": 1_000_000.0,
                    "reason": "日涨幅偏离值",
                    "source": "Tushare top_list",
                    "updated_at": "2026-05-22T18:30:00",
                }
            ]
        )

    def fetch_top_inst(self, trade_date):
        return pd.DataFrame(
            [
                {
                    "code": "000001.SZ",
                    "trade_date": "2026-05-22",
                    "exalter": "机构专用",
                    "net_buy": 500_000.0,
                    "source": "Tushare top_inst",
                    "updated_at": "2026-05-22T18:30:00",
                }
            ]
        )

    def fetch_hm_detail(self, trade_date):
        return pd.DataFrame(
            [
                {
                    "code": "000001.SZ",
                    "trade_date": "2026-05-22",
                    "name": "平安银行",
                    "hm_name": "作手新一",
                    "net_amount": 300_000.0,
                    "source": "Tushare hm_detail",
                    "updated_at": "2026-05-22T18:30:00",
                }
            ]
        )


def test_tushare_daily_basic_updates_float_values_and_data_map(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ"), _stock("600000.SH")], ["code"])
    service = UpdateService(db)
    warnings = []

    count = service._update_tushare_daily_basic(
        date(2026, 5, 22),
        FakeTushareEnrichmentSource(),
        warnings,
    )
    DataService(db).refresh_capabilities()

    daily_row = db.query("SELECT * FROM tushare_daily_basic WHERE code = '000001.SZ'")[0]
    float_row = db.query("SELECT * FROM float_market_values WHERE code = '000001.SZ'")[0]
    capabilities = {row["capability"]: row for row in DataService(db).capabilities()}
    assert count == 1
    assert warnings == []
    assert daily_row["circ_mv"] == 12_300_000.0
    assert float_row["float_market_value"] == 12_300_000.0
    assert float_row["float_shares"] == 1_000_000.0
    assert float_row["source"] == "Tushare daily_basic"
    assert capabilities["每日指标"]["coverage_count"] == 1
    assert capabilities["流通市值"]["coverage_count"] == 1


def test_tushare_enrichment_update_persists_all_capability_tables(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert("stock_basic", [_stock("000001.SZ"), _stock("600000.SH")], ["code"])
    monkeypatch.setattr(update_module, "TushareEnrichmentSource", FakeFullTushareEnrichmentSource)
    service = UpdateService(db)
    warnings = []

    counts = service._update_tushare_enrichment(
        date(2026, 5, 22),
        include_bj=False,
        exclude_star=False,
        warnings=warnings,
    )
    DataService(db).refresh_capabilities()
    capabilities = {row["capability"]: row for row in DataService(db).capabilities()}

    assert warnings == []
    assert counts["stk_factor"] == 1
    assert counts["moneyflow"] == 1
    assert counts["limit_list_d"] == 1
    assert counts["cyq_perf"] == 1
    assert counts["cyq_chips"] == 1
    assert counts["ths_member"] == 1
    assert counts["top_list"] == 1
    assert counts["top_inst"] == 1
    assert counts["hm_detail"] == 1
    assert db.scalar("SELECT limit_type FROM tushare_limit_list_d WHERE code = '000001.SZ'") == "U"
    assert capabilities["技术因子"]["coverage_count"] == 1
    assert capabilities["资金流向"]["coverage_count"] == 1
    assert capabilities["涨跌停"]["coverage_count"] == 1
    assert capabilities["筹码分布"]["coverage_count"] == 1
    assert capabilities["概念/行业成分"]["coverage_count"] == 1
    assert capabilities["龙虎榜/游资"]["coverage_count"] == 1
