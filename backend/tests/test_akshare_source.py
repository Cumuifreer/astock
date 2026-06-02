from datetime import date, datetime

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
