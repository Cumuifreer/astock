from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.update_service import UpdateService


def test_float_market_value_is_estimated_from_local_history_turnover(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "daily_snapshots",
        [
            {
                "code": "000001.SZ",
                "date": "2026-05-20",
                "name": "平安银行",
                "latest_price": 10.0,
                "pct_chg": 1.2,
                "high": 10.5,
                "low": 9.8,
                "volume": 1200.0,
                "amount": 12_000.0,
                "turnover_rate": None,
                "float_market_value": None,
                "source": "Tushare 实时日线",
                "updated_at": "2026-05-20T10:00:00",
            },
            {
                "code": "600000.SH",
                "date": "2026-05-20",
                "name": "浦发银行",
                "latest_price": 8.0,
                "pct_chg": -0.5,
                "high": 8.2,
                "low": 7.9,
                "volume": 800.0,
                "amount": 6_400.0,
                "turnover_rate": None,
                "float_market_value": None,
                "source": "Tushare 实时日线",
                "updated_at": "2026-05-20T10:00:00",
            },
        ],
        ["code", "date"],
    )
    db.upsert(
        "historical_bars",
        [
            {
                "code": "000001.SZ",
                "date": "2026-05-19",
                "open": 9.7,
                "high": 10.1,
                "low": 9.5,
                "close": 9.9,
                "prev_close": 9.6,
                "volume": 1000.0,
                "amount": 9_900.0,
                "turn": 2.0,
                "pct_chg": 3.1,
                "tradestatus": "1",
                "is_st": False,
                "source": "Tushare daily 前复权",
                "updated_at": "2026-05-19T15:00:00",
            },
            {
                "code": "600000.SH",
                "date": "2026-05-19",
                "open": 8.1,
                "high": 8.2,
                "low": 8.0,
                "close": 8.0,
                "prev_close": 8.1,
                "volume": 1000.0,
                "amount": 8_000.0,
                "turn": 0.0,
                "pct_chg": -1.2,
                "tradestatus": "1",
                "is_st": False,
                "source": "Tushare daily 前复权",
                "updated_at": "2026-05-19T15:00:00",
            },
        ],
        ["code", "date"],
    )

    count = UpdateService(db)._update_float_values_from_snapshots()

    rows = db.query("SELECT * FROM float_market_values ORDER BY code")
    assert count == 1
    assert len(rows) == 1
    assert rows[0]["code"] == "000001.SZ"
    assert rows[0]["float_shares"] == 50_000.0
    assert rows[0]["float_market_value"] == 500_000.0
    assert rows[0]["source"] == "本地历史换手率估算"
