from datetime import date, datetime

import pandas as pd

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.data_service import DataService
from backend.app.services.update_service import UpdateService


class FakeTushareIndexSource:
    def fetch_index_daily(self, index_codes, trade_date):
        assert index_codes[:2] == ["000001.SH", "399107.SZ"]
        assert trade_date == date(2026, 5, 24)
        return pd.DataFrame(
            [
                {
                    "index_code": "000001.SH",
                    "trade_date": "2026-05-24",
                    "close": 3100.0,
                    "pct_chg": 1.2,
                    "amount": 450000000000.0,
                    "source": "Tushare index_daily",
                    "updated_at": "2026-05-24T17:00:00",
                },
                {
                    "index_code": "399107.SZ",
                    "trade_date": "2026-05-24",
                    "close": 2100.0,
                    "pct_chg": -0.2,
                    "amount": 500000000000.0,
                    "source": "Tushare index_daily",
                    "updated_at": "2026-05-24T17:00:00",
                },
            ]
        )


def _bar(code: str, pct_chg: float, amount: float) -> dict:
    return {
        "code": code,
        "date": date(2026, 5, 24),
        "open": 10.0,
        "high": 10.8,
        "low": 9.8,
        "close": 10.2,
        "prev_close": 10.0,
        "volume": 1000.0,
        "amount": amount,
        "turn": 2.0,
        "pct_chg": pct_chg,
        "tradestatus": "1",
        "is_st": False,
        "source": "test",
        "updated_at": datetime(2026, 5, 24, 15, 0),
    }


def test_market_environment_persists_index_and_breadth_scores(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "stock_basic",
        [
            {
                "code": code,
                "name": code,
                "exchange": code.split(".")[-1],
                "list_date": date(2020, 1, 1),
                "source": "test",
                "is_st": False,
                "suspended": suspended,
                "updated_at": datetime(2026, 5, 24, 9, 0),
            }
            for code, suspended in [
                ("000001.SZ", False),
                ("000002.SZ", False),
                ("600000.SH", False),
                ("600001.SH", False),
                ("000003.SZ", True),
            ]
        ],
        ["code"],
    )
    db.upsert(
        "historical_bars",
        [
            _bar("000001.SZ", 2.0, 100000000),
            _bar("000002.SZ", 1.0, 200000000),
            _bar("600000.SH", -1.0, 150000000),
            _bar("600001.SH", 0.0, 120000000),
            _bar("000003.SZ", 9.0, 900000000),
        ],
        ["code", "date"],
    )
    db.upsert(
        "tushare_limit_list_d",
        [
            {
                "code": "000001.SZ",
                "trade_date": date(2026, 5, 24),
                "name": "平安银行",
                "limit_type": "U",
                "source": "Tushare limit_list_d",
                "updated_at": datetime(2026, 5, 24, 15, 0),
            }
        ],
        ["code", "trade_date"],
    )

    count = UpdateService(db)._update_market_environment(date(2026, 5, 24), FakeTushareIndexSource())
    DataService(db).refresh_capabilities()
    environment = db.query("SELECT * FROM market_environment WHERE date = '2026-05-24'")[0]
    capabilities = {row["capability"]: row for row in DataService(db).capabilities()}

    assert count == 1
    assert db.scalar("SELECT COUNT(*) FROM tushare_index_daily") == 2
    assert environment["up_count"] == 2
    assert environment["down_count"] == 1
    assert environment["total_amount"] == 570000000
    assert environment["limit_up_count"] == 1
    assert environment["trend_score"] > 0
    assert capabilities["市场环境"]["coverage_count"] == 1
    assert capabilities["市场环境"]["missing_count"] == 0


def test_market_turnover_score_uses_active_stock_baseline(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "stock_basic",
        [
            {
                "code": "000001.SZ",
                "name": "000001.SZ",
                "exchange": "SZ",
                "list_date": date(2020, 1, 1),
                "source": "test",
                "is_st": False,
                "suspended": False,
                "updated_at": datetime(2026, 5, 24, 9, 0),
            },
            {
                "code": "000003.SZ",
                "name": "000003.SZ",
                "exchange": "SZ",
                "list_date": date(2020, 1, 1),
                "source": "test",
                "is_st": False,
                "suspended": True,
                "updated_at": datetime(2026, 5, 24, 9, 0),
            },
        ],
        ["code"],
    )
    inactive_bar = _bar("000003.SZ", 2.0, 900)
    inactive_bar["date"] = date(2026, 5, 23)
    active_bar = _bar("000001.SZ", 2.0, 100)
    active_bar["date"] = date(2026, 5, 23)
    db.upsert("historical_bars", [active_bar, inactive_bar], ["code", "date"])

    _, ratio = UpdateService(db)._market_turnover_score(date(2026, 5, 24), total_amount=200)

    assert ratio == 2


def _sector_row(
    code: str,
    name: str,
    trade_date: date,
    *,
    sector_type: str = "concept",
    pct_chg: float = 1.0,
    amount: float = 10_000_000,
    net_amount=None,
    limit_up_count=None,
    limit_up_count_status: str | None = None,
    strong_count=None,
    strong_count_status: str | None = "computed",
    heat_score: float = 60,
) -> dict:
    return {
        "sector_code": code,
        "sector_name": name,
        "sector_type": sector_type,
        "trade_date": trade_date,
        "pct_chg": pct_chg,
        "amount": amount,
        "net_amount": net_amount,
        "company_count": 20,
        "member_count": 20,
        "limit_up_count": limit_up_count,
        "limit_up_count_status": limit_up_count_status,
        "strong_count": strong_count,
        "strong_count_status": strong_count_status,
        "limit_data_date": trade_date if limit_up_count_status == "computed" else None,
        "quote_data_date": trade_date,
        "leader_code": "000001.SZ",
        "leader_name": "平安银行",
        "leader_pct_chg": 3.0,
        "heat_score": heat_score,
        "source": "test",
        "updated_at": datetime(2026, 5, 29, 12, 0),
    }


def test_sector_heatmap_filters_non_theme_concept_rows(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "market_sector_daily",
        [
            _sector_row("885001.TI", "同花顺全A(沪深京)", date(2026, 5, 29), heat_score=99),
            _sector_row("885002.TI", "QFII重仓", date(2026, 5, 29), heat_score=98),
            _sector_row("885003.TI", "昨日涨停", date(2026, 5, 29), heat_score=97),
            _sector_row("885004.TI", "OLED", date(2026, 5, 29), heat_score=80),
            _sector_row("885005.TI", "超级电容", date(2026, 5, 28), heat_score=90),
        ],
        ["sector_code", "sector_type", "trade_date"],
    )

    rows = DataService(db).sector_heatmap("concept", "heat", limit=10)

    assert [row["name"] for row in rows] == ["OLED"]
    assert rows[0]["trade_date"] == date(2026, 5, 29)


def test_sector_heatmap_uses_latest_eligible_metric_date(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "market_sector_daily",
        [
            _sector_row("885001.TI", "OLED", date(2026, 5, 29), net_amount=None, limit_up_count=None, limit_up_count_status="daily_only", strong_count=6),
            _sector_row("885002.TI", "超级电容", date(2026, 5, 28), net_amount=120_000_000, limit_up_count=4, limit_up_count_status="computed", strong_count=8, heat_score=88),
            _sector_row("885003.TI", "医美概念", date(2026, 5, 28), net_amount=80_000_000, limit_up_count=2, limit_up_count_status="computed", strong_count=5, heat_score=78),
        ],
        ["sector_code", "sector_type", "trade_date"],
    )

    money_rows = DataService(db).sector_heatmap("concept", "moneyflow", limit=10)
    limit_rows = DataService(db).sector_heatmap("concept", "limit", limit=10)

    assert {row["trade_date"] for row in money_rows} == {date(2026, 5, 28)}
    assert [row["name"] for row in money_rows] == ["超级电容", "医美概念"]
    assert {row["trade_date"] for row in limit_rows} == {date(2026, 5, 28)}
    assert [row["limit_up_count_status"] for row in limit_rows] == ["computed", "computed"]


def test_sector_heatmap_returns_empty_when_metric_has_no_eligible_rows(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "market_sector_daily",
        [
            _sector_row("885001.TI", "OLED", date(2026, 5, 29), net_amount=None, limit_up_count=None, limit_up_count_status="daily_only"),
        ],
        ["sector_code", "sector_type", "trade_date"],
    )

    assert DataService(db).sector_heatmap("concept", "moneyflow", limit=10) == []
    assert DataService(db).sector_heatmap("concept", "limit", limit=10) == []
