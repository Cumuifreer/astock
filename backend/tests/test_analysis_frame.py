import pandas as pd

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


def test_analysis_frame_filters_stale_current_bars_and_merges_stock_basic_st(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "stock_basic",
        [
            {
                "code": "000001.SZ",
                "name": "平安银行",
                "exchange": "SZ",
                "list_date": "1991-04-03",
                "source": "test",
                "is_st": False,
                "suspended": False,
                "updated_at": "2026-05-20T15:00:00",
            },
            {
                "code": "000002.SZ",
                "name": "ST 测试",
                "exchange": "SZ",
                "list_date": "1991-04-03",
                "source": "test",
                "is_st": True,
                "suspended": False,
                "updated_at": "2026-05-20T15:00:00",
            },
            {
                "code": "000003.SZ",
                "name": "过期 K 线",
                "exchange": "SZ",
                "list_date": "1991-04-03",
                "source": "test",
                "is_st": False,
                "suspended": False,
                "updated_at": "2026-05-20T15:00:00",
            },
        ],
        ["code"],
    )
    db.upsert(
        "historical_bars",
        [
            {
                "code": "000001.SZ",
                "date": "2026-05-20",
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
                "source": "Tushare daily",
                "updated_at": "2026-05-20T15:00:00",
            },
            {
                "code": "000002.SZ",
                "date": "2026-05-20",
                "open": 8.8,
                "high": 9.1,
                "low": 8.7,
                "close": 9.0,
                "prev_close": 8.8,
                "volume": 1000.0,
                "amount": 10_000.0,
                "turn": 2.0,
                "pct_chg": 2.0,
                "tradestatus": "1",
                "is_st": False,
                "source": "Tushare daily",
                "updated_at": "2026-05-20T15:00:00",
            },
            {
                "code": "000003.SZ",
                "date": "2026-05-19",
                "open": 7.8,
                "high": 8.1,
                "low": 7.7,
                "close": 8.0,
                "prev_close": 7.8,
                "volume": 1000.0,
                "amount": 10_000.0,
                "turn": 2.0,
                "pct_chg": 2.0,
                "tradestatus": "1",
                "is_st": False,
                "source": "Tushare daily",
                "updated_at": "2026-05-19T15:00:00",
            },
        ],
        ["code", "date"],
    )

    frame = AnalysisService(db)._build_analysis_frame(DEFAULT_STRATEGY_CONFIG)

    assert set(frame["code"]) == {"000001.SZ", "000002.SZ"}
    assert bool(frame[frame["code"] == "000002.SZ"].iloc[0]["is_st"]) is True


def test_analysis_frame_uses_event_features_only_on_analysis_date_and_keeps_age(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "historical_bars",
        [
            {
                "code": "000001.SZ",
                "date": "2026-05-20",
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
                "source": "Tushare daily",
                "updated_at": "2026-05-20T15:00:00",
            }
        ],
        ["code", "date"],
    )
    db.upsert(
        "tushare_limit_list_d",
        [
            {
                "code": "000001.SZ",
                "trade_date": "2026-05-19",
                "name": "平安银行",
                "close": 10.0,
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
    db.upsert(
        "tushare_top_list",
        [
            {
                "code": "000001.SZ",
                "trade_date": "2026-05-19",
                "name": "平安银行",
                "net_amount": 8_000_000.0,
                "amount_rate": 2.5,
                "reason": "日涨幅偏离值达7%",
                "source": "Tushare top_list",
                "updated_at": "2026-05-19T17:00:00",
            }
        ],
        ["code", "trade_date", "reason"],
    )

    row = AnalysisService(db)._build_analysis_frame(DEFAULT_STRATEGY_CONFIG).iloc[0]

    assert row.get("limit_type") is None or pd.isna(row.get("limit_type"))
    assert row.get("top_list_net_amount") is None or pd.isna(row.get("top_list_net_amount"))
    assert row["days_since_limit_event"] == 1
    assert row["days_since_top_list"] == 1


def test_theme_metrics_use_as_of_membership_and_exact_limit_event_date(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "historical_bars",
        [
            {
                "code": "000001.SZ",
                "date": "2026-05-20",
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
                "source": "Tushare daily",
                "updated_at": "2026-05-20T15:00:00",
            },
            {
                "code": "000002.SZ",
                "date": "2026-05-20",
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
                "source": "Tushare daily",
                "updated_at": "2026-05-20T15:00:00",
            },
        ],
        ["code", "date"],
    )
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
                "updated_at": "2026-05-20T15:00:00",
            },
            {
                "code": "000002.SZ",
                "name": "万科A",
                "con_code": "885001.TI",
                "con_name": "测试题材",
                "weight": None,
                "in_date": "2026-01-01",
                "out_date": "2026-05-19",
                "is_new": "N",
                "source": "Tushare ths_member",
                "updated_at": "2026-05-20T15:00:00",
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
                "close": 10.0,
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

    row = AnalysisService(db)._build_analysis_frame(DEFAULT_STRATEGY_CONFIG, as_of_date="2026-05-20")
    active = row[row["code"] == "000001.SZ"].iloc[0]
    expired = row[row["code"] == "000002.SZ"].iloc[0]

    assert active["topic_count"] == 1
    assert active["theme_limit_count"] == 0
    assert expired["topic_count"] == 0


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


def test_analysis_frame_enriches_tushare_feature_parameters(tmp_path):
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
                "source": "Tushare daily",
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
                "volume": 1800.0,
                "amount": 18_900.0,
                "turn": 3.0,
                "pct_chg": 5.0,
                "tradestatus": "1",
                "is_st": False,
                "source": "Tushare daily",
                "updated_at": "2026-05-19T15:00:00",
            },
        ],
        ["code", "date"],
    )
    db.upsert(
        "tushare_daily_basic",
        [
            {
                "code": "000001.SZ",
                "trade_date": "2026-05-19",
                "turnover_rate": 3.6,
                "volume_ratio": 1.8,
                "circ_mv": 12_000_000_000.0,
                "total_mv": 18_000_000_000.0,
                "source": "Tushare daily_basic",
                "updated_at": "2026-05-19T17:00:00",
            }
        ],
        ["code", "trade_date"],
    )
    db.upsert(
        "tushare_moneyflow",
        [
            {
                "code": "000001.SZ",
                "trade_date": "2026-05-19",
                "buy_lg_amount": 800_000.0,
                "sell_lg_amount": 300_000.0,
                "buy_elg_amount": 1_000_000.0,
                "sell_elg_amount": 400_000.0,
                "main_net_amount": 1_100_000.0,
                "net_mf_amount": 900_000.0,
                "source": "Tushare moneyflow",
                "updated_at": "2026-05-19T17:00:00",
            }
        ],
        ["code", "trade_date"],
    )
    db.upsert(
        "tushare_limit_list_d",
        [
            {
                "code": "000001.SZ",
                "trade_date": "2026-05-19",
                "name": "平安银行",
                "close": 10.5,
                "pct_chg": 10.0,
                "limit_type": "U",
                "fd_amount": 240_000_000.0,
                "open_times": 1,
                "source": "Tushare limit_list_d",
                "updated_at": "2026-05-19T17:00:00",
            }
        ],
        ["code", "trade_date"],
    )
    db.upsert(
        "tushare_cyq_perf",
        [
            {
                "code": "000001.SZ",
                "trade_date": "2026-05-19",
                "winner_rate": 0.62,
                "cost_15pct": 9.2,
                "cost_50pct": 10.0,
                "cost_85pct": 11.5,
                "source": "Tushare cyq_perf",
                "updated_at": "2026-05-19T17:00:00",
            }
        ],
        ["code", "trade_date"],
    )
    db.upsert(
        "tushare_cyq_chips",
        [
            {"code": "000001.SZ", "trade_date": "2026-05-19", "price": 9.5, "percent": 0.2, "source": "Tushare cyq_chips", "updated_at": "2026-05-19T17:00:00"},
            {"code": "000001.SZ", "trade_date": "2026-05-19", "price": 10.2, "percent": 0.35, "source": "Tushare cyq_chips", "updated_at": "2026-05-19T17:00:00"},
        ],
        ["code", "trade_date", "price"],
    )
    db.upsert(
        "tushare_top_list",
        [
            {
                "code": "000001.SZ",
                "trade_date": "2026-05-19",
                "name": "平安银行",
                "net_amount": 8_000_000.0,
                "amount_rate": 2.5,
                "reason": "日涨幅偏离值达7%",
                "source": "Tushare top_list",
                "updated_at": "2026-05-19T17:00:00",
            }
        ],
        ["code", "trade_date", "reason"],
    )
    db.upsert(
        "tushare_top_inst",
        [
            {
                "code": "000001.SZ",
                "trade_date": "2026-05-19",
                "exalter": "机构专用",
                "net_buy": 3_000_000.0,
                "source": "Tushare top_inst",
                "updated_at": "2026-05-19T17:00:00",
            }
        ],
        ["code", "trade_date", "exalter"],
    )
    db.upsert(
        "tushare_hm_detail",
        [
            {
                "code": "000001.SZ",
                "trade_date": "2026-05-19",
                "name": "平安银行",
                "hm_name": "测试席位",
                "net_amount": 2_000_000.0,
                "source": "Tushare hm_detail",
                "updated_at": "2026-05-19T17:00:00",
            }
        ],
        ["code", "trade_date", "hm_name"],
    )

    frame = AnalysisService(db)._build_analysis_frame(DEFAULT_STRATEGY_CONFIG)
    row = frame[frame["code"] == "000001.SZ"].iloc[0]

    assert row["turnover_rate"] == 3.6
    assert row["volume_ratio"] == 1.8
    assert row["float_market_value"] == 12_000_000_000.0
    assert row["main_net_amount"] == 1_100_000.0
    assert row["large_net_amount"] == 500_000.0
    assert row["super_large_net_amount"] == 600_000.0
    assert row["limit_type"] == "U"
    assert row["limit_open_times"] == 1
    assert row["limit_fd_mv_ratio"] == 0.02
    assert row["cyq_winner_rate"] == 0.62
    assert row["price_to_cost_50pct"] == 0.05
    assert row["cyq_chip_peak_percent"] == 0.35
    assert row["top_list_net_amount"] == 8_000_000.0
    assert row["top_inst_net_buy"] == 3_000_000.0
    assert row["hot_money_net_amount"] == 2_000_000.0
    assert row["data_sources"]["moneyflow"] == "Tushare moneyflow"
    assert row["feature_dates"]["moneyflow"] == "2026-05-19"
