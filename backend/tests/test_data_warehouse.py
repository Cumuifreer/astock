from datetime import date, datetime

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.data_service import CAPABILITY_DEFINITIONS, DataService


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


def test_stock_warehouse_filters_inactive_status_and_falls_back_for_exact_code_search(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    seed_stock_basics(db)
    db.upsert(
        "stock_basic",
        [
            {
                "code": "000003.SZ",
                "name": "PT金田A",
                "exchange": "SZ",
                "list_date": date(1991, 7, 3),
                "source": "test",
                "is_st": False,
                "suspended": True,
                "updated_at": datetime(2026, 5, 24, 9, 0),
            }
        ],
        ["code"],
    )

    service = DataService(db)
    active = service.list_stocks()
    inactive = service.list_stocks(status="inactive")
    all_rows = service.list_stocks(status="all")
    exact_search = service.list_stocks(search="000003.SZ")
    six_digit_search = service.list_stocks(search="000003")

    assert active["total"] == 4
    assert [row["code"] for row in inactive["rows"]] == ["000003.SZ"]
    assert inactive["rows"][0]["is_active"] is False
    assert inactive["rows"][0]["status_label"] == "非活跃"
    assert all_rows["total"] == 5
    assert exact_search["total"] == 1
    assert exact_search["rows"][0]["code"] == "000003.SZ"
    assert six_digit_search["total"] == 1
    assert six_digit_search["rows"][0]["code"] == "000003.SZ"


def test_capability_definitions_declare_coverage_kind_explicitly():
    assert CAPABILITY_DEFINITIONS
    assert all(definition.get("coverage_kind") in {"stock", "event", "dataset"} for definition in CAPABILITY_DEFINITIONS.values())


def test_stock_warehouse_turnover_rate_prefers_tushare_daily_basic(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    seed_stock_basics(db)
    db.upsert(
        "tushare_daily_basic",
        [
            {
                "code": "000001.SZ",
                "trade_date": date(2026, 5, 24),
                "turnover_rate": 2.4,
                "volume_ratio": 1.7,
                "source": "Tushare daily_basic",
                "updated_at": datetime(2026, 5, 24, 17, 0),
            }
        ],
        ["code", "trade_date"],
    )

    result = DataService(db).list_stocks(search="000001")

    assert result["rows"][0]["turnover_rate"] == 2.4


def test_stock_warehouse_volume_ratio_falls_back_to_local_history(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    seed_stock_basics(db)
    db.upsert(
        "historical_bars",
        [
            {
                "code": "000001.SZ",
                "date": date(2026, 5, 22),
                "open": 9.8,
                "high": 10.0,
                "low": 9.7,
                "close": 9.9,
                "prev_close": 9.8,
                "volume": 100,
                "amount": 1000000,
                "turn": 0.8,
                "pct_chg": 1.0,
                "source": "test",
                "updated_at": datetime(2026, 5, 22, 15, 0),
            },
            {
                "code": "000001.SZ",
                "date": date(2026, 5, 23),
                "open": 10.0,
                "high": 10.2,
                "low": 9.9,
                "close": 10.1,
                "prev_close": 9.9,
                "volume": 200,
                "amount": 2000000,
                "turn": 1.0,
                "pct_chg": 2.0,
                "source": "test",
                "updated_at": datetime(2026, 5, 23, 15, 0),
            },
            {
                "code": "000001.SZ",
                "date": date(2026, 5, 24),
                "open": 10.2,
                "high": 10.5,
                "low": 10.0,
                "close": 10.4,
                "prev_close": 10.1,
                "volume": 300,
                "amount": 3000000,
                "turn": 1.2,
                "pct_chg": 3.0,
                "source": "test",
                "updated_at": datetime(2026, 5, 24, 15, 0),
            },
        ],
        ["code", "date"],
    )

    service = DataService(db)
    result = service.list_stocks(search="000001")
    detail = service.stock_detail("000001.SZ")

    assert result["rows"][0]["volume_ratio"] == 2.0
    assert detail["daily_basic"]["volume_ratio"] == 2.0
    assert detail["daily_basic"]["volume_ratio_source"] == "本地K线"


def test_overview_reports_active_and_inactive_stock_counts(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    seed_stock_basics(db)
    db.upsert(
        "stock_basic",
        [
            {
                "code": "000003.SZ",
                "name": "PT金田A",
                "exchange": "SZ",
                "list_date": date(1991, 7, 3),
                "source": "test",
                "is_st": False,
                "suspended": True,
                "updated_at": datetime(2026, 5, 24, 9, 0),
            }
        ],
        ["code"],
    )

    overview = DataService(db).overview()

    assert overview["stock_count"] == 5
    assert overview["active_stock_count"] == 4
    assert overview["inactive_stock_count"] == 1
    assert overview["turnover_coverage"]["total"] == 4


def test_capabilities_count_snapshot_float_market_value(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    seed_stock_basics(db)

    capabilities = DataService(db).capabilities()
    float_market_value = next(row for row in capabilities if row["capability"] == "流通市值")

    assert float_market_value["coverage_count"] == 1
    assert str(float_market_value["latest_update"]).startswith("2026-05-24")


def test_capabilities_use_active_stocks_as_denominator(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    seed_stock_basics(db)
    db.upsert(
        "stock_basic",
        [
            {
                "code": "000003.SZ",
                "name": "PT金田A",
                "exchange": "SZ",
                "list_date": date(1991, 7, 3),
                "source": "test",
                "is_st": False,
                "suspended": True,
                "updated_at": datetime(2026, 5, 24, 9, 0),
            }
        ],
        ["code"],
    )

    capabilities = {row["capability"]: row for row in DataService(db).capabilities()}

    assert capabilities["股票基础信息"]["coverage_count"] == 4
    assert capabilities["股票基础信息"]["missing_count"] == 0
    assert capabilities["当天行情快照"]["missing_count"] == 3


def test_capabilities_hide_stale_fallback_failures_when_current_source_is_healthy(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    seed_stock_basics(db)
    active_codes = ["000001.SZ", "300750.SZ", "688981.SH", "600519.SH"]
    snapshot_rows = []
    history_rows = []
    for code in active_codes:
        snapshot_rows.append(
            {
                "code": code,
                "date": date(2026, 5, 28),
                "name": code,
                "latest_price": 10.0,
                "pct_chg": 0.0,
                "high": 10.2,
                "low": 9.8,
                "volume": 100,
                "amount": 100000000,
                "turnover_rate": 1.2,
                "float_market_value": 1000000000,
                "source": "Tushare 实时日线",
                "updated_at": datetime(2026, 5, 28, 15, 0),
            }
        )
        history_rows.append(
            {
                "code": code,
                "date": date(2026, 5, 27),
                "open": 9.8,
                "high": 10.2,
                "low": 9.7,
                "close": 10.0,
                "prev_close": 9.9,
                "volume": 1000000,
                "amount": 100000000,
                "turn": 1.2,
                "pct_chg": 1.0,
                "tradestatus": "1",
                "is_st": False,
                "source": "Tushare daily 前复权",
                "updated_at": datetime(2026, 5, 28, 1, 49),
            }
        )
    db.upsert("daily_snapshots", snapshot_rows, ["code", "date"])
    db.upsert("historical_bars", history_rows, ["code", "date"])
    db.upsert(
        "market_sector_daily",
        [
            {
                "sector_code": "885800.TI",
                "sector_name": "半导体设备",
                "sector_type": "concept",
                "trade_date": date(2026, 5, 27),
                "pct_chg": 1.2,
                "amount": 100000000,
                "net_amount": 1000000,
                "company_count": 10,
                "limit_up_count": 1,
                "strong_count": 3,
                "leader_code": "000001.SZ",
                "leader_name": "平安银行",
                "heat_score": 66.0,
                "source": "Tushare moneyflow_cnt_ths",
                "updated_at": datetime(2026, 5, 28, 2, 1),
            }
        ],
        ["sector_code", "sector_type", "trade_date"],
    )
    db.upsert(
        "source_status",
        [
            {
                "source": "AData",
                "capability": "当天行情快照",
                "status": "available",
                "last_checked": datetime(2026, 5, 20, 3, 9),
                "last_success": datetime(2026, 5, 20, 3, 9),
                "last_failure": None,
                "failure_reason": None,
                "ttl_until": datetime(2026, 5, 20, 4, 9),
                "payload_json": {},
            },
            {
                "source": "AkShare 新浪",
                "capability": "当天行情快照",
                "status": "failed",
                "last_checked": datetime(2026, 5, 28, 1, 19),
                "last_success": None,
                "last_failure": datetime(2026, 5, 28, 1, 19),
                "failure_reason": "Can not decode value starting with character '<'",
                "ttl_until": datetime(2026, 5, 28, 2, 19),
                "payload_json": {},
            },
            {
                "source": "Tushare 实时日线",
                "capability": "当天行情快照",
                "status": "available",
                "last_checked": datetime(2026, 5, 28, 1, 28),
                "last_success": datetime(2026, 5, 28, 1, 28),
                "last_failure": None,
                "failure_reason": None,
                "ttl_until": datetime(2026, 5, 28, 2, 28),
                "payload_json": {"rows": 4},
            },
            {
                "source": "Baostock",
                "capability": "历史 K 线",
                "status": "failed",
                "last_checked": datetime(2026, 5, 25, 7, 35),
                "last_success": None,
                "last_failure": datetime(2026, 5, 25, 7, 35),
                "failure_reason": "002402.SZ: 当前 AData 2.9.5 历史行情接口内部使用 EM 源，已按项目约束跳过。",
                "ttl_until": datetime(2026, 5, 25, 8, 35),
                "payload_json": {},
            },
            {
                "source": "Tushare daily 前复权",
                "capability": "历史 K 线",
                "status": "available",
                "last_checked": datetime(2026, 5, 28, 1, 49),
                "last_success": datetime(2026, 5, 28, 1, 49),
                "last_failure": None,
                "failure_reason": None,
                "ttl_until": datetime(2026, 5, 28, 2, 49),
                "payload_json": {"rows": 4},
            },
            {
                "source": "Legacy board source",
                "capability": "板块热力",
                "status": "available",
                "last_checked": datetime(2026, 5, 20, 1, 0),
                "last_success": datetime(2026, 5, 20, 1, 0),
                "last_failure": None,
                "failure_reason": None,
                "ttl_until": datetime(2026, 5, 20, 2, 0),
                "payload_json": {"rows": 1},
            },
            {
                "source": "Tushare moneyflow_cnt_ths",
                "capability": "板块热力",
                "status": "available",
                "last_checked": datetime(2026, 5, 28, 2, 1, 11),
                "last_success": datetime(2026, 5, 28, 2, 1, 11),
                "last_failure": None,
                "failure_reason": None,
                "ttl_until": datetime(2026, 5, 28, 3, 1, 11),
                "payload_json": {"rows": 386},
            },
            {
                "source": "Tushare moneyflow_ind_ths",
                "capability": "板块热力",
                "status": "available",
                "last_checked": datetime(2026, 5, 28, 2, 1, 12),
                "last_success": datetime(2026, 5, 28, 2, 1, 12),
                "last_failure": None,
                "failure_reason": None,
                "ttl_until": datetime(2026, 5, 28, 3, 1, 12),
                "payload_json": {"rows": 90},
            },
        ],
        ["source", "capability"],
    )

    capabilities = {row["capability"]: row for row in DataService(db).capabilities()}

    assert capabilities["当天行情快照"]["missing_count"] == 0
    assert capabilities["当天行情快照"]["last_failure_reason"] is None
    assert capabilities["当天行情快照"]["actual_sources"] == ["Tushare 实时日线"]
    assert capabilities["历史 K 线"]["missing_count"] == 0
    assert capabilities["历史 K 线"]["last_failure_reason"] is None
    assert capabilities["历史 K 线"]["actual_sources"] == ["Tushare daily 前复权"]
    assert set(capabilities["板块热力"]["actual_sources"]) == {"Tushare moneyflow_cnt_ths", "Tushare moneyflow_ind_ths"}


def test_capabilities_ignore_inactive_old_data_in_stock_coverage(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    seed_stock_basics(db)
    db.upsert(
        "stock_basic",
        [
            {
                "code": "000003.SZ",
                "name": "PT金田A",
                "exchange": "SZ",
                "list_date": date(1991, 7, 3),
                "source": "test",
                "is_st": False,
                "suspended": True,
                "updated_at": datetime(2026, 5, 24, 9, 0),
            }
        ],
        ["code"],
    )
    db.upsert(
        "historical_bars",
        [
            {
                "code": "000003.SZ",
                "date": date(2026, 5, 24),
                "open": 1.0,
                "high": 1.1,
                "low": 0.9,
                "close": 1.0,
                "prev_close": 1.0,
                "volume": 100,
                "amount": 1000,
                "turn": 1.0,
                "pct_chg": 0.0,
                "tradestatus": "1",
                "is_st": False,
                "source": "test",
                "updated_at": datetime(2026, 5, 24, 15, 0),
            }
        ],
        ["code", "date"],
    )

    capabilities = {row["capability"]: row for row in DataService(db).capabilities()}

    assert capabilities["历史 K 线"]["coverage_count"] == 0
    assert capabilities["历史 K 线"]["missing_count"] == 4


def test_capabilities_include_tushare_enrichment_layers(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    seed_stock_basics(db)

    capabilities = DataService(db).capabilities()
    by_name = {row["capability"]: row for row in capabilities}

    for name in ["每日指标", "技术因子", "资金流向", "涨跌停", "筹码分布", "概念/行业成分", "龙虎榜/游资"]:
        assert name in by_name
        assert "Tushare" in " ".join(by_name[name]["fallback_sources"])
    assert by_name["每日指标"]["participates_in_analysis"] is True
    for name in ["资金流向", "涨跌停", "筹码分布", "概念/行业成分", "龙虎榜/游资"]:
        assert by_name[name]["participates_in_analysis"] is True


def test_capabilities_treat_event_datasets_as_event_counts_and_drop_legacy_concept_label(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    seed_stock_basics(db)
    db.upsert(
        "data_capabilities",
        [
            {
                "capability": "概念标签",
                "actual_sources": [],
                "fallback_sources": [],
                "coverage_count": 0,
                "missing_count": 4,
                "latest_update": None,
                "last_failure_reason": None,
                "uses_cache": True,
                "can_backfill": False,
                "participates_in_analysis": False,
                "updated_at": datetime(2026, 5, 24, 15, 0),
            }
        ],
        ["capability"],
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

    capabilities = DataService(db).capabilities()
    by_name = {row["capability"]: row for row in capabilities}

    assert "概念标签" not in by_name
    assert by_name["涨跌停"]["coverage_count"] == 1
    assert by_name["涨跌停"]["missing_count"] == 0


def test_stock_warehouse_detail_includes_tushare_enrichment_profile(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    seed_stock_basics(db)
    db.upsert(
        "tushare_daily_basic",
        [
            {
                "code": "000001.SZ",
                "trade_date": date(2026, 5, 24),
                "turnover_rate": 2.4,
                "volume_ratio": 1.7,
                "circ_mv": 1200000000,
                "source": "Tushare daily_basic",
                "updated_at": datetime(2026, 5, 24, 17, 0),
            }
        ],
        ["code", "trade_date"],
    )
    db.upsert(
        "tushare_moneyflow",
        [
            {
                "code": "000001.SZ",
                "trade_date": date(2026, 5, 24),
                "net_mf_amount": 1000000,
                "main_net_amount": 2500000,
                "source": "Tushare moneyflow",
                "updated_at": datetime(2026, 5, 24, 17, 0),
            }
        ],
        ["code", "trade_date"],
    )
    db.upsert(
        "tushare_cyq_perf",
        [
            {
                "code": "000001.SZ",
                "trade_date": date(2026, 5, 24),
                "winner_rate": 0.62,
                "cost_50pct": 10.8,
                "source": "Tushare cyq_perf",
                "updated_at": datetime(2026, 5, 24, 17, 0),
            }
        ],
        ["code", "trade_date"],
    )
    db.upsert(
        "tushare_ths_member",
        [
            {
                "code": "000001.SZ",
                "name": "平安银行",
                "con_code": "885800.TI",
                "con_name": "银行",
                "source": "Tushare ths_member",
                "updated_at": datetime(2026, 5, 24, 17, 0),
            }
        ],
        ["code", "con_code"],
    )

    detail = DataService(db).stock_detail("000001.SZ")

    assert detail["basic"]["code"] == "000001.SZ"
    assert detail["daily_basic"]["volume_ratio"] == 1.7
    assert detail["moneyflow"]["main_net_amount"] == 2500000
    assert detail["cyq_perf"]["winner_rate"] == 0.62
    assert detail["concepts"][0]["con_name"] == "银行"
