from datetime import date, datetime

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.data_service import DataService


def seed_stock_basics(db: Database) -> None:
    db.upsert(
        "stock_basic",
        [
            {
                "code": "000001.SZ",
                "name": "平安银行",
                "exchange": "SZ",
                "list_date": date(1991, 4, 3),
                "source": "test",
                "is_st": False,
                "suspended": False,
                "updated_at": datetime(2026, 5, 24, 9, 0),
            },
            {
                "code": "300750.SZ",
                "name": "宁德时代",
                "exchange": "SZ",
                "list_date": date(2018, 6, 11),
                "source": "test",
                "is_st": False,
                "suspended": False,
                "updated_at": datetime(2026, 5, 24, 9, 0),
            },
            {
                "code": "688981.SH",
                "name": "中芯国际",
                "exchange": "SH",
                "list_date": date(2020, 7, 16),
                "source": "test",
                "is_st": False,
                "suspended": False,
                "updated_at": datetime(2026, 5, 24, 9, 0),
            },
            {
                "code": "600519.SH",
                "name": "贵州茅台",
                "exchange": "SH",
                "list_date": date(2001, 8, 27),
                "source": "test",
                "is_st": False,
                "suspended": False,
                "updated_at": datetime(2026, 5, 24, 9, 0),
            },
        ],
        ["code"],
    )
    db.upsert(
        "daily_snapshots",
        [
            {
                "code": "000001.SZ",
                "date": date(2026, 5, 24),
                "name": "平安银行",
                "latest_price": 10.0,
                "pct_chg": 0.0,
                "high": 10.2,
                "low": 9.8,
                "volume": 100,
                "amount": 100000000,
                "turnover_rate": 1.2,
                "float_market_value": 1000000000,
                "source": "test",
                "updated_at": datetime(2026, 5, 24, 15, 0),
            }
        ],
        ["code", "date"],
    )


def test_stock_warehouse_search_qualifies_joined_code_columns(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    seed_stock_basics(db)

    result = DataService(db).list_stocks(search="000")

    assert result["total"] == 1
    assert result["rows"][0]["code"] == "000001.SZ"


def test_stock_warehouse_filters_by_exchange_and_board(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    seed_stock_basics(db)
    service = DataService(db)

    sz = service.list_stocks(exchange="SZ")
    star = service.list_stocks(board="star")
    main = service.list_stocks(board="main")

    assert [row["code"] for row in sz["rows"]] == ["000001.SZ", "300750.SZ"]
    assert [row["code"] for row in star["rows"]] == ["688981.SH"]
    assert [row["code"] for row in main["rows"]] == ["000001.SZ", "600519.SH"]


def test_capabilities_count_snapshot_float_market_value(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    seed_stock_basics(db)

    capabilities = DataService(db).capabilities()
    float_market_value = next(row for row in capabilities if row["capability"] == "流通市值")

    assert float_market_value["coverage_count"] == 1
    assert str(float_market_value["latest_update"]).startswith("2026-05-24")
