from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.analysis_service import AnalysisService
from backend.app.services.strategy_service import DEFAULT_STRATEGY_CONFIG


def test_analysis_frame_keeps_zero_snapshot_values(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "historical_bars",
        [
            {
                "code": "000001.SZ",
                "date": "2026-05-18",
                "open": 9.8,
                "high": 10.1,
                "low": 9.7,
                "close": 10.0,
                "prev_close": 9.8,
                "volume": 1000.0,
                "amount": 10_000.0,
                "turn": 2.0,
                "pct_chg": 2.0,
                "tradestatus": "1",
                "is_st": False,
                "source": "Baostock",
                "updated_at": "2026-05-18T15:00:00",
            },
            {
                "code": "000001.SZ",
                "date": "2026-05-19",
                "open": 10.0,
                "high": 10.8,
                "low": 9.9,
                "close": 10.5,
                "prev_close": 10.0,
                "volume": 1200.0,
                "amount": 12_600.0,
                "turn": 3.0,
                "pct_chg": 5.0,
                "tradestatus": "1",
                "is_st": False,
                "source": "Baostock",
                "updated_at": "2026-05-19T15:00:00",
            },
        ],
        ["code", "date"],
    )
    db.upsert(
        "daily_snapshots",
        [
            {
                "code": "000001.SZ",
                "date": "2026-05-20",
                "name": "平安银行",
                "latest_price": 10.5,
                "pct_chg": 0.0,
                "high": 10.5,
                "low": 10.5,
                "volume": 0.0,
                "amount": 0.0,
                "turnover_rate": 0.0,
                "float_market_value": 0.0,
                "source": "AkShare 新浪",
                "updated_at": "2026-05-20T10:00:00",
            }
        ],
        ["code", "date"],
    )
    db.upsert(
        "float_market_values",
        [
            {
                "code": "000001.SZ",
                "date": "2026-05-20",
                "float_shares": 1000.0,
                "float_market_value": 0.0,
                "source": "Baostock 换手率估算",
                "updated_at": "2026-05-20T10:00:00",
            }
        ],
        ["code", "date"],
    )

    frame = AnalysisService(db)._build_analysis_frame(DEFAULT_STRATEGY_CONFIG)
    row = frame.iloc[0]

    assert row["pct_chg"] == 0.0
    assert row["amount"] == 0.0
    assert row["volume"] == 0.0
    assert row["turnover_rate"] == 0.0
    assert row["float_market_value"] == 0.0
    assert row["volume_ratio"] == 0.0
