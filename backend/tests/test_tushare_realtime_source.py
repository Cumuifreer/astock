import pandas as pd

from backend.app.sources.tushare_source import TushareEnrichmentSource, TushareRealtimeSource


class FakeTusharePro:
    def rt_k(self, ts_code=""):
        assert "0*.SZ" in ts_code
        return pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "name": "平安银行",
                    "close": 10.5,
                    "pre_close": 10.0,
                    "open": 10.1,
                    "high": 10.8,
                    "low": 10.0,
                    "vol": 1200,
                    "amount": 12_600_000,
                },
                {
                    "ts_code": "688001.SH",
                    "name": "华兴源创",
                    "close": 20.5,
                    "pre_close": 20.0,
                    "open": 20.1,
                    "high": 21.0,
                    "low": 20.0,
                    "vol": 800,
                    "amount": 16_400_000,
                },
            ]
        )


def test_tushare_realtime_daily_normalizes_snapshot_fields():
    source = TushareRealtimeSource(pro=FakeTusharePro())

    frame = source.fetch_realtime_daily(include_bj=False, exclude_star=True)

    assert list(frame["code"]) == ["000001.SZ"]
    row = frame.iloc[0].to_dict()
    assert row["name"] == "平安银行"
    assert row["latest_price"] == 10.5
    assert row["pct_chg"] == 5.0
    assert row["high"] == 10.8
    assert row["low"] == 10.0
    assert row["volume"] == 1200.0
    assert row["amount"] == 12_600_000.0
    assert row["source"] == "Tushare 实时日线"


class FakeTushareEnrichmentPro:
    def daily_basic(self, trade_date="", fields=""):
        assert trade_date == "20260522"
        assert "circ_mv" in fields
        return pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260522",
                    "close": 12.3,
                    "turnover_rate": 2.5,
                    "turnover_rate_f": 3.1,
                    "volume_ratio": 1.8,
                    "total_share": 200.0,
                    "float_share": 100.0,
                    "free_share": 80.0,
                    "total_mv": 2460.0,
                    "circ_mv": 1230.0,
                }
            ]
        )

    def stk_factor(self, trade_date="", fields=""):
        assert trade_date == "20260522"
        return pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260522",
                    "macd": 0.12,
                    "kdj_k": 55.0,
                    "kdj_d": 48.0,
                    "kdj_j": 69.0,
                    "rsi_6": 60.0,
                    "boll_upper": 13.0,
                    "boll_mid": 12.0,
                    "boll_lower": 11.0,
                }
            ]
        )

    def moneyflow(self, trade_date="", fields=""):
        assert trade_date == "20260522"
        return pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260522",
                    "buy_lg_amount": 30.0,
                    "sell_lg_amount": 10.0,
                    "buy_elg_amount": 40.0,
                    "sell_elg_amount": 20.0,
                    "net_mf_amount": 25.0,
                }
            ]
        )

    def limit_list_d(self, trade_date="", fields=""):
        assert trade_date == "20260522"
        return pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260522",
                    "name": "平安银行",
                    "limit": "U",
                    "up_stat": "1/1",
                    "fd_amount": 1000000.0,
                    "open_times": 2,
                }
            ]
        )

    def ths_member(self, con_code="", fields=""):
        assert con_code == "000001.SZ"
        return pd.DataFrame(
            [
                {
                    "ts_code": "885800.TI",
                    "con_code": "000001.SZ",
                    "con_name": "平安银行",
                    "is_new": "Y",
                }
            ]
        )


def test_tushare_enrichment_source_normalizes_daily_batch_endpoints():
    source = TushareEnrichmentSource(pro=FakeTushareEnrichmentPro())

    daily_basic = source.fetch_daily_basic("2026-05-22")
    factors = source.fetch_stk_factor("2026-05-22")
    moneyflow = source.fetch_moneyflow("2026-05-22")
    limits = source.fetch_limit_list_d("2026-05-22")
    members = source.fetch_ths_member_for_codes(["000001.SZ"], limit=1)

    assert daily_basic.iloc[0]["code"] == "000001.SZ"
    assert daily_basic.iloc[0]["trade_date"] == "2026-05-22"
    assert daily_basic.iloc[0]["circ_mv"] == 12_300_000.0
    assert daily_basic.iloc[0]["float_share"] == 1_000_000.0
    assert factors.iloc[0]["macd"] == 0.12
    assert moneyflow.iloc[0]["main_net_amount"] == 400_000.0
    assert limits.iloc[0]["limit"] == "U"
    assert members.iloc[0]["code"] == "000001.SZ"
    assert members.iloc[0]["con_code"] == "885800.TI"
