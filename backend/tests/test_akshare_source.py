import json
from datetime import date, datetime
from types import SimpleNamespace

import pandas as pd

from backend.app.sources import akshare_source as akshare_module
from backend.app.sources.akshare_source import AkShareSource


def test_akshare_snapshot_date_uses_shanghai_calendar_day(monkeypatch):
    class FakeServerDate:
        @classmethod
        def today(cls):
            return date(2026, 6, 1)

    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 2, 0, 30, tzinfo=tz)

        @classmethod
        def utcnow(cls):
            return datetime(2026, 6, 1, 16, 30)

    monkeypatch.setattr(akshare_module, "date", FakeServerDate)
    monkeypatch.setattr(akshare_module, "datetime", FakeDateTime)

    frame = AkShareSource()._normalize_snapshot(
        pd.DataFrame(
            [
                {
                    "代码": "000001",
                    "名称": "平安银行",
                    "最新价": 10.5,
                }
            ]
        ),
        AkShareSource.sina_name,
        include_bj=False,
        exclude_star=False,
    )

    assert frame.iloc[0]["date"] == "2026-06-02"


def test_sina_snapshot_uses_controlled_pagination_and_keeps_raw_market_fields(monkeypatch):
    rows = [
        {
            "symbol": f"600{index:03d}",
            "name": f"股票{index}",
            "trade": "10.5",
            "changepercent": "1.2",
            "high": "10.8",
            "low": "10.1",
            "volume": "1000",
            "amount": "10500",
            "turnoverratio": "2.5",
            "nmc": "123.4",
        }
        for index in range(81)
    ]

    class Response:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    class Session:
        def __init__(self):
            self.headers = {}
            self.calls = []

        def get(self, url, params=None, timeout=None):
            self.calls.append((url, params, timeout))
            if "getHQNodeStockCount" in url:
                return Response("81")
            page = int(params["page"])
            return Response(json.dumps(rows[:80] if page == 1 else rows[80:]))

    session = Session()
    sleeps = []
    monkeypatch.setattr(
        akshare_module,
        "settings",
        SimpleNamespace(
            sina_total_timeout_seconds=30,
            sina_request_timeout_seconds=5,
            sina_page_min_delay=0.1,
            sina_page_max_delay=0.1,
        ),
    )
    monkeypatch.setattr(akshare_module.time, "sleep", sleeps.append)

    frame = AkShareSource().fetch_sina_snapshot(session=session)

    assert len(frame) == 81
    assert len(session.calls) == 3
    assert sleeps == [0.1]
    assert frame.iloc[0]["turnover_rate"] == 2.5
    assert frame.iloc[0]["float_market_value"] == 1_234_000
