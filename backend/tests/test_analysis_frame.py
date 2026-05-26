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


def test_analysis_frame_enriches_theme_metrics(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    bars = []
    for code, first_close, second_close in [
        ("000001.SZ", 10.0, 11.0),
        ("000002.SZ", 8.0, 8.8),
    ]:
        bars.extend(
            [
                {
                    "code": code,
                    "date": "2026-05-18",
                    "open": first_close,
                    "high": first_close * 1.02,
                    "low": first_close * 0.98,
                    "close": first_close,
                    "prev_close": first_close * 0.99,
                    "volume": 1000.0,
                    "amount": first_close * 1000.0,
                    "turn": 2.0,
                    "pct_chg": 1.0,
                    "tradestatus": "1",
                    "is_st": False,
                    "source": "Tushare daily",
                    "updated_at": "2026-05-18T15:00:00",
                },
                {
                    "code": code,
                    "date": "2026-05-19",
                    "open": first_close,
                    "high": second_close * 1.01,
                    "low": first_close * 0.99,
                    "close": second_close,
                    "prev_close": first_close,
                    "volume": 1800.0,
                    "amount": second_close * 1800.0,
                    "turn": 3.0,
                    "pct_chg": 10.0,
                    "tradestatus": "1",
                    "is_st": False,
                    "source": "Tushare daily",
                    "updated_at": "2026-05-19T15:00:00",
                },
            ]
        )
    db.upsert("historical_bars", bars, ["code", "date"])
    db.upsert(
        "tushare_ths_member",
        [
            {
                "code": "000001.SZ",
                "name": "平安银行",
                "con_code": "885001.TI",
                "con_name": "测试题材",
                "weight": None,
                "in_date": "2026-01-01",
                "out_date": None,
                "is_new": "Y",
                "source": "Tushare ths_member",
                "updated_at": "2026-05-19T15:00:00",
            },
            {
                "code": "000002.SZ",
                "name": "万科A",
                "con_code": "885001.TI",
                "con_name": "测试题材",
                "weight": None,
                "in_date": "2026-01-01",
                "out_date": None,
                "is_new": "Y",
                "source": "Tushare ths_member",
                "updated_at": "2026-05-19T15:00:00",
            },
        ],
        ["code", "con_code"],
    )
    db.upsert(
        "tushare_limit_list_d",
        [
            {
                "code": "000002.SZ",
                "trade_date": "2026-05-19",
                "name": "万科A",
                "close": 8.8,
                "pct_chg": 10.0,
                "limit_type": "U",
                "up_stat": "1/1",
                "fd_amount": 100000000.0,
                "first_time": "09:40:00",
                "last_time": "14:50:00",
                "open_times": 0,
                "source": "Tushare limit_list_d",
                "updated_at": "2026-05-19T15:00:00",
            }
        ],
        ["code", "trade_date"],
    )

    frame = AnalysisService(db)._build_analysis_frame(DEFAULT_STRATEGY_CONFIG)
    row = frame[frame["code"] == "000001.SZ"].iloc[0]

    assert row["topic_count"] == 1
    assert row["concept_count"] == 1
    assert row["theme_limit_count"] == 1
    assert row["topic_heat"] > 0
