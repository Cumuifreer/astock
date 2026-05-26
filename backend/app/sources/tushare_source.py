from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from backend.app.services.market_utils import normalize_a_share_code, safe_float
from backend.app.sources.base import SourceUnavailable, first_present
from backend.app.sources.tushare_client import create_tushare_pro


CHINA_TZ = ZoneInfo("Asia/Shanghai")


class TushareRealtimeSource:
    name = "Tushare 实时日线"

    def __init__(
        self,
        pro: Optional[Any] = None,
        ts_module: Optional[Any] = None,
        token: Optional[str] = None,
        http_url: Optional[str] = None,
    ) -> None:
        self._pro = pro
        self._ts_module = ts_module
        self._token = token
        self._http_url = http_url

    @property
    def client(self) -> tuple[Any, Any]:
        if self._pro is None:
            self._ts_module, self._pro = create_tushare_pro(self._token, self._http_url)
        return self._ts_module, self._pro

    def fetch_realtime_daily(
        self,
        include_bj: bool = False,
        exclude_star: bool = False,
        code_list: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        frame = self._fetch_raw_frame(code_list=code_list, include_bj=include_bj)
        return self._normalize_frame(frame, include_bj=include_bj, exclude_star=exclude_star)

    def _fetch_raw_frame(self, code_list: Optional[List[str]] = None, include_bj: bool = False) -> pd.DataFrame:
        ts_module, pro = self.client
        codes = ",".join(code_list or [])

        if hasattr(pro, "rt_k"):
            patterns = codes or ("0*.SZ,3*.SZ,6*.SH,9*.BJ" if include_bj else "0*.SZ,3*.SZ,6*.SH")
            frame = pro.rt_k(ts_code=patterns)
            frame.attrs["tushare_amount_unit"] = "yuan"
            return frame

        if hasattr(pro, "realtime_quote"):
            try:
                frame = pro.realtime_quote(ts_code=codes) if codes else pro.realtime_quote()
            except TypeError:
                frame = pro.realtime_quote()
            frame.attrs["tushare_amount_unit"] = "yuan"
            return frame

        if hasattr(ts_module, "realtime_quote"):
            try:
                frame = ts_module.realtime_quote(ts_code=codes) if codes else ts_module.realtime_quote()
            except TypeError:
                frame = ts_module.realtime_quote()
            frame.attrs["tushare_amount_unit"] = "yuan"
            return frame

        if hasattr(pro, "daily"):
            trade_date = datetime.now(CHINA_TZ).strftime("%Y%m%d")
            try:
                frame = pro.daily(ts_code=codes, trade_date=trade_date) if codes else pro.daily(trade_date=trade_date)
            except TypeError:
                frame = pro.daily(trade_date=trade_date)
            frame.attrs["tushare_amount_unit"] = "thousand_yuan"
            return frame

        raise SourceUnavailable("当前 Tushare 中转未提供 rt_k、realtime_quote 或 daily 实时日线接口。")

    def _normalize_frame(
        self,
        frame: pd.DataFrame,
        include_bj: bool,
        exclude_star: bool,
    ) -> pd.DataFrame:
        if frame is None or frame.empty:
            raise SourceUnavailable("Tushare 实时日线返回空数据。")
        rows: List[Dict[str, Any]] = []
        today = datetime.now(CHINA_TZ).date().isoformat()
        amount_unit = frame.attrs.get("tushare_amount_unit", "yuan")
        for item in frame.to_dict("records"):
            code = normalize_a_share_code(
                first_present(item, ["ts_code", "TS_CODE", "code", "CODE", "symbol", "SYMBOL"]),
                include_bj=include_bj,
                exclude_star=exclude_star,
            )
            if not code:
                continue
            latest = safe_float(
                first_present(item, ["price", "PRICE", "latest_price", "LATEST_PRICE", "close", "CLOSE"])
            )
            pre_close = safe_float(first_present(item, ["pre_close", "PRE_CLOSE", "昨收"]))
            pct_chg = safe_float(
                first_present(
                    item,
                    ["pct_chg", "PCT_CHG", "pct_change", "PCT_CHANGE", "changepercent", "涨跌幅"],
                )
            )
            if pct_chg is None and latest is not None and pre_close is not None and pre_close > 0:
                pct_chg = (latest - pre_close) / pre_close * 100
            amount = _normalize_tushare_amount(
                first_present(item, ["amount", "AMOUNT", "成交额"]),
                amount_unit=amount_unit,
            )
            rows.append(
                {
                    "code": code,
                    "date": _normalize_trade_date(first_present(item, ["trade_date", "TRADE_DATE"])) or today,
                    "name": first_present(item, ["name", "NAME", "股票名称"]) or code,
                    "latest_price": latest,
                    "pct_chg": pct_chg,
                    "high": safe_float(first_present(item, ["high", "HIGH", "最高", "最高价"])),
                    "low": safe_float(first_present(item, ["low", "LOW", "最低", "最低价"])),
                    "volume": safe_float(first_present(item, ["vol", "VOL", "volume", "VOLUME", "成交量"])),
                    "amount": amount,
                    "turnover_rate": safe_float(first_present(item, ["turnover_rate", "TURNOVER_RATE", "turn", "TURN"])),
                    "float_market_value": safe_float(
                        first_present(item, ["float_market_value", "FLOAT_MARKET_VALUE", "circ_mv", "CIRC_MV"])
                    ),
                    "source": self.name,
                    "updated_at": datetime.utcnow(),
                }
            )
        result = pd.DataFrame(rows)
        if result.empty:
            raise SourceUnavailable("Tushare 实时日线没有匹配到真实 A 股代码。")
        return result


def _normalize_trade_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    if len(text) >= 10:
        return text[:10]
    return None


def _normalize_tushare_amount(value: Any, amount_unit: str) -> Optional[float]:
    amount = safe_float(value)
    if amount is None:
        return None
    if amount_unit == "thousand_yuan":
        return amount * 1000
    return amount
