import pandas as pd

from backend.app.sources.tushare_source import TushareRealtimeSource


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
