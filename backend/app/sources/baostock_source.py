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

    def fetch_stock_basics(self, include_bj: bool = False, exclude_star: bool = False) -> pd.DataFrame:
        with self.session() as bs:
            rs = bs.query_stock_basic()
            frame = _rs_to_frame(rs)
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

    def fetch_history(self, code: str, start_date: date, end_date: date) -> pd.DataFrame:
        fields = (
            "date,code,open,high,low,close,preclose,volume,amount,"
            "adjustflag,turn,tradestatus,pctChg,isST"
        )
        with self.session() as bs:
            rs = bs.query_history_k_data_plus(
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
                    "tradestatus": str(item.get("tradestatus") or ""),
                    "is_st": safe_bool_from_flag(item.get("isST")),
                    "source": self.name,
                    "updated_at": datetime.utcnow(),
                }
            )
        return pd.DataFrame([row for row in rows if row.get("date")])


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
