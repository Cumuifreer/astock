from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Dict, Iterator, List, Optional

import pandas as pd

from backend.app.services.market_utils import (
    normalize_a_share_code,
    safe_bool_from_flag,
    safe_float,
    to_baostock_code,
)


class BaostockSource:
    name = "Baostock"

    def __init__(self) -> None:
        self._bs = None

    @property
    def bs(self) -> Any:
        if self._bs is None:
            import baostock as bs  # type: ignore

            self._bs = bs
        return self._bs

    @contextmanager
    def session(self) -> Iterator[Any]:
        bs = self.bs
        login = bs.login()
        if getattr(login, "error_code", "0") != "0":
            raise RuntimeError(getattr(login, "error_msg", "Baostock 登录失败"))
        try:
            yield bs
        finally:
            bs.logout()

    def fetch_stock_basics(
        self,
        include_bj: bool = False,
        exclude_star: bool = False,
        client: Any = None,
    ) -> pd.DataFrame:
        if client is None:
            with self.session() as bs:
                return self.fetch_stock_basics(include_bj, exclude_star, client=bs)
        frame = _rs_to_frame(client.query_stock_basic())
        rows: List[Dict[str, Any]] = []
        for _, item in frame.iterrows():
            if str(item.get("type") or "1") != "1":
                continue
            raw = item.get("code")
            code = normalize_a_share_code(raw, include_bj=include_bj, exclude_star=exclude_star)
            if not code:
                continue
            rows.append(
                {
                    "code": code,
                    "name": item.get("code_name") or item.get("name") or code,
                    "exchange": code.split(".")[1],
                    "list_date": _date_or_none(item.get("ipoDate")),
                    "source": self.name,
                    "is_st": False,
                    "suspended": str(item.get("status") or "1") != "1",
                    "updated_at": datetime.utcnow(),
                }
            )
        return pd.DataFrame(rows)

    def fetch_history(
        self,
        code: str,
        start_date: date,
        end_date: date,
        client: Any = None,
    ) -> pd.DataFrame:
        fields = (
            "date,code,open,high,low,close,preclose,volume,amount,"
            "adjustflag,turn,tradestatus,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST"
        )
        if client is None:
            with self.session() as bs:
                return self.fetch_history(code, start_date, end_date, client=bs)
        rs = client.query_history_k_data_plus(
                to_baostock_code(code),
                fields,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                frequency="d",
                adjustflag="2",
            )
        frame = _rs_to_frame(rs)
        rows: List[Dict[str, Any]] = []
        for _, item in frame.iterrows():
            normalized = normalize_a_share_code(item.get("code"))
            if not normalized:
                continue
            rows.append(
                {
                    "code": normalized,
                    "date": _date_or_none(item.get("date")),
                    "open": safe_float(item.get("open")),
                    "high": safe_float(item.get("high")),
                    "low": safe_float(item.get("low")),
                    "close": safe_float(item.get("close")),
                    "prev_close": safe_float(item.get("preclose")),
                    "volume": safe_float(item.get("volume")),
                    "amount": safe_float(item.get("amount")),
                    "turn": safe_float(item.get("turn")),
                    "pct_chg": safe_float(item.get("pctChg")),
                    "pe_ttm": safe_float(item.get("peTTM")),
                    "pb_mrq": safe_float(item.get("pbMRQ")),
                    "ps_ttm": safe_float(item.get("psTTM")),
                    "pcf_ncf_ttm": safe_float(item.get("pcfNcfTTM")),
                    "tradestatus": str(item.get("tradestatus") or ""),
                    "is_st": safe_bool_from_flag(item.get("isST")),
                    "source": self.name,
                    "updated_at": datetime.utcnow(),
                }
            )
        return pd.DataFrame([row for row in rows if row.get("date")])

    def fetch_trade_calendar(self, start_date: date, end_date: date, client: Any = None) -> pd.DataFrame:
        if client is None:
            with self.session() as bs:
                return self.fetch_trade_calendar(start_date, end_date, client=bs)
        rs = client.query_trade_dates(
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
        )
        frame = _rs_to_frame(rs)
        now = datetime.utcnow()
        return pd.DataFrame(
            [
                {
                    "date": _date_or_none(item.get("calendar_date")),
                    "is_trading_day": str(item.get("is_trading_day") or "0") == "1",
                    "source": self.name,
                    "updated_at": now,
                }
                for item in frame.to_dict("records")
                if _date_or_none(item.get("calendar_date"))
            ]
        )

    def fetch_stock_industry(self, client: Any = None) -> pd.DataFrame:
        if client is None:
            with self.session() as bs:
                return self.fetch_stock_industry(client=bs)
        frame = _rs_to_frame(client.query_stock_industry())
        now = datetime.utcnow()
        rows = []
        for item in frame.to_dict("records"):
            code = normalize_a_share_code(item.get("code"))
            if not code:
                continue
            rows.append(
                {
                    "code": code,
                    "name": item.get("code_name") or code,
                    "industry": item.get("industry") or None,
                    "classification": item.get("industryClassification") or None,
                    "source": self.name,
                    "updated_at": now,
                }
            )
        return pd.DataFrame(rows)

    def fetch_index_history(
        self,
        codes: List[str],
        start_date: date,
        end_date: date,
        client: Any = None,
    ) -> pd.DataFrame:
        if client is None:
            with self.session() as bs:
                return self.fetch_index_history(codes, start_date, end_date, client=bs)
        rows: List[Dict[str, Any]] = []
        fields = "date,code,open,high,low,close,preclose,volume,amount,pctChg"
        now = datetime.utcnow()
        for code in codes:
            rs = client.query_history_k_data_plus(
                to_baostock_code(code),
                fields,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                frequency="d",
                adjustflag="3",
            )
            frame = _rs_to_frame(rs)
            for item in frame.to_dict("records"):
                index_code = normalize_a_share_code(item.get("code"))
                trade_date = _date_or_none(item.get("date"))
                if not index_code or not trade_date:
                    continue
                rows.append(
                    {
                        "index_code": index_code,
                        "trade_date": trade_date,
                        "open": safe_float(item.get("open")),
                        "high": safe_float(item.get("high")),
                        "low": safe_float(item.get("low")),
                        "close": safe_float(item.get("close")),
                        "pre_close": safe_float(item.get("preclose")),
                        "pct_chg": safe_float(item.get("pctChg")),
                        "volume": safe_float(item.get("volume")),
                        "amount": safe_float(item.get("amount")),
                        "source": self.name,
                        "updated_at": now,
                    }
                )
        return pd.DataFrame(rows)


def _rs_to_frame(rs: Any) -> pd.DataFrame:
    if getattr(rs, "error_code", "0") != "0":
        raise RuntimeError(getattr(rs, "error_msg", "Baostock 查询失败"))
    data = []
    while rs.next():
        data.append(rs.get_row_data())
    return pd.DataFrame(data, columns=getattr(rs, "fields", None))


def _date_or_none(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    return str(value)[:10]
