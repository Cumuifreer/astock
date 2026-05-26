from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from backend.app.config import settings
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


class TushareEnrichmentSource:
    name = "Tushare Pro"

    HISTORY_DAILY_FIELDS = "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
    HISTORY_DAILY_BASIC_FIELDS = "ts_code,trade_date,turnover_rate"
    ADJ_FACTOR_FIELDS = "ts_code,trade_date,adj_factor"
    DAILY_BASIC_FIELDS = (
        "ts_code,trade_date,close,turnover_rate,turnover_rate_f,volume_ratio,"
        "pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,free_share,total_mv,circ_mv"
    )
    STK_FACTOR_FIELDS = (
        "ts_code,trade_date,macd,kdj_k,kdj_d,kdj_j,rsi_6,rsi_12,rsi_24,"
        "boll_upper,boll_mid,boll_lower,cci"
    )
    MONEYFLOW_FIELDS = (
        "ts_code,trade_date,buy_sm_amount,sell_sm_amount,buy_md_amount,sell_md_amount,"
        "buy_lg_amount,sell_lg_amount,buy_elg_amount,sell_elg_amount,net_mf_amount"
    )
    LIMIT_LIST_FIELDS = "trade_date,ts_code,name,close,pct_chg,up_stat,limit,fd_amount,first_time,last_time,open_times"
    CYQ_PERF_FIELDS = (
        "ts_code,trade_date,his_low,his_high,cost_5pct,cost_15pct,cost_50pct,"
        "cost_85pct,cost_95pct,weight_avg,winner_rate"
    )
    CYQ_CHIPS_FIELDS = "ts_code,trade_date,price,percent"
    THS_MEMBER_FIELDS = "ts_code,code,name,con_code,con_name,weight,in_date,out_date,is_new"
    TOP_LIST_FIELDS = (
        "trade_date,ts_code,name,close,pct_change,turnover_rate,amount,l_sell,l_buy,"
        "l_amount,net_amount,net_rate,amount_rate,float_values,reason"
    )
    TOP_INST_FIELDS = "trade_date,ts_code,exalter,buy,buy_rate,sell,sell_rate,net_buy"
    HM_DETAIL_FIELDS = "trade_date,ts_code,ts_name,name,hm_name,buy_amount,sell_amount,net_amount"
    INDEX_DAILY_FIELDS = "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"

    def __init__(
        self,
        pro: Optional[Any] = None,
        ts_module: Optional[Any] = None,
        token: Optional[str] = None,
        http_url: Optional[str] = None,
        loop_delay: Optional[float] = None,
    ) -> None:
        self._pro = pro
        self._ts_module = ts_module
        self._token = token
        self._http_url = http_url
        self._loop_delay = settings.tushare_enrichment_loop_delay if loop_delay is None else loop_delay

    @property
    def client(self) -> tuple[Any, Any]:
        if self._pro is None:
            self._ts_module, self._pro = create_tushare_pro(self._token, self._http_url)
        return self._ts_module, self._pro

    def fetch_history_bars(self, start_date: Any, end_date: Any, codes: Optional[List[str]] = None) -> pd.DataFrame:
        start = _date_from_arg(start_date)
        end = _date_from_arg(end_date)
        if start > end:
            return pd.DataFrame()

        requested = set(codes or [])
        daily_rows: List[Dict[str, Any]] = []
        factors: Dict[tuple[str, str], float] = {}
        latest_factor_by_code: Dict[str, float] = {}
        turns: Dict[tuple[str, str], Optional[float]] = {}

        for day in _date_span(start, end):
            if day.weekday() >= 5:
                continue
            trade_date = _trade_date_arg(day)
            daily_frame = self._call_api("daily", trade_date=trade_date, fields=self.HISTORY_DAILY_FIELDS)
            self._sleep_between_codes()
            day_daily_rows = _records(daily_frame)
            if not day_daily_rows:
                continue

            factor_frame = self._call_api("adj_factor", trade_date=trade_date, fields=self.ADJ_FACTOR_FIELDS)
            self._sleep_between_codes()
            try:
                basic_frame = self._call_api(
                    "daily_basic",
                    trade_date=trade_date,
                    fields=self.HISTORY_DAILY_BASIC_FIELDS,
                )
            except Exception:
                basic_frame = pd.DataFrame()
            self._sleep_between_codes()

            for item in _records(factor_frame):
                code = normalize_a_share_code(first_present(item, ["ts_code", "TS_CODE"]), include_bj=True)
                trade_day = _normalize_trade_date(first_present(item, ["trade_date", "TRADE_DATE"]))
                factor = safe_float(first_present(item, ["adj_factor", "ADJ_FACTOR"]))
                if not code or not trade_day or factor is None:
                    continue
                if requested and code not in requested:
                    continue
                factors[(code, trade_day)] = factor
                latest_factor_by_code[code] = factor

            for item in _records(basic_frame):
                code = normalize_a_share_code(first_present(item, ["ts_code", "TS_CODE"]), include_bj=True)
                trade_day = _normalize_trade_date(first_present(item, ["trade_date", "TRADE_DATE"]))
                if not code or not trade_day:
                    continue
                if requested and code not in requested:
                    continue
                turns[(code, trade_day)] = safe_float(first_present(item, ["turnover_rate", "TURNOVER_RATE"]))

            for item in day_daily_rows:
                code = normalize_a_share_code(first_present(item, ["ts_code", "TS_CODE"]), include_bj=True)
                trade_day = _normalize_trade_date(first_present(item, ["trade_date", "TRADE_DATE"]))
                if not code or not trade_day:
                    continue
                if requested and code not in requested:
                    continue
                daily_rows.append({"code": code, "date": trade_day, "raw": item})

        rows: List[Dict[str, Any]] = []
        for item in daily_rows:
            code = item["code"]
            trade_day = item["date"]
            raw = item["raw"]
            factor = factors.get((code, trade_day))
            latest_factor = latest_factor_by_code.get(code)
            if factor is None or latest_factor in (None, 0):
                continue
            scale = factor / latest_factor
            rows.append(
                {
                    "code": code,
                    "date": trade_day,
                    "open": _scaled_float(first_present(raw, ["open", "OPEN"]), scale),
                    "high": _scaled_float(first_present(raw, ["high", "HIGH"]), scale),
                    "low": _scaled_float(first_present(raw, ["low", "LOW"]), scale),
                    "close": _scaled_float(first_present(raw, ["close", "CLOSE"]), scale),
                    "prev_close": _scaled_float(first_present(raw, ["pre_close", "PRE_CLOSE"]), scale),
                    "volume": _hands_to_shares(first_present(raw, ["vol", "VOL", "volume", "VOLUME"])),
                    "amount": _normalize_tushare_amount(
                        first_present(raw, ["amount", "AMOUNT"]),
                        amount_unit="thousand_yuan",
                    ),
                    "turn": turns.get((code, trade_day)),
                    "pct_chg": safe_float(first_present(raw, ["pct_chg", "PCT_CHG"])),
                    "tradestatus": "1",
                    "is_st": None,
                    "source": "Tushare daily 前复权",
                    "updated_at": datetime.utcnow(),
                }
            )
        if daily_rows and not rows:
            raise SourceUnavailable("Tushare adj_factor 为空，无法生成前复权历史 K 线。")
        return _clean_frame(rows, required=["code", "date"])

    def fetch_daily_basic(self, trade_date: Any) -> pd.DataFrame:
        frame = self._call_api("daily_basic", trade_date=_trade_date_arg(trade_date), fields=self.DAILY_BASIC_FIELDS)
        rows = []
        for item in _records(frame):
            code = normalize_a_share_code(first_present(item, ["ts_code", "TS_CODE"]))
            if not code:
                continue
            rows.append(
                {
                    "code": code,
                    "trade_date": _normalize_trade_date(first_present(item, ["trade_date", "TRADE_DATE"])),
                    "close": safe_float(first_present(item, ["close", "CLOSE"])),
                    "turnover_rate": safe_float(first_present(item, ["turnover_rate", "TURNOVER_RATE"])),
                    "turnover_rate_f": safe_float(first_present(item, ["turnover_rate_f", "TURNOVER_RATE_F"])),
                    "volume_ratio": safe_float(first_present(item, ["volume_ratio", "VOLUME_RATIO"])),
                    "pe": safe_float(first_present(item, ["pe", "PE"])),
                    "pe_ttm": safe_float(first_present(item, ["pe_ttm", "PE_TTM"])),
                    "pb": safe_float(first_present(item, ["pb", "PB"])),
                    "ps": safe_float(first_present(item, ["ps", "PS"])),
                    "ps_ttm": safe_float(first_present(item, ["ps_ttm", "PS_TTM"])),
                    "dv_ratio": safe_float(first_present(item, ["dv_ratio", "DV_RATIO"])),
                    "dv_ttm": safe_float(first_present(item, ["dv_ttm", "DV_TTM"])),
                    "total_share": _ten_thousand_unit(first_present(item, ["total_share", "TOTAL_SHARE"])),
                    "float_share": _ten_thousand_unit(first_present(item, ["float_share", "FLOAT_SHARE"])),
                    "free_share": _ten_thousand_unit(first_present(item, ["free_share", "FREE_SHARE"])),
                    "total_mv": _ten_thousand_unit(first_present(item, ["total_mv", "TOTAL_MV"])),
                    "circ_mv": _ten_thousand_unit(first_present(item, ["circ_mv", "CIRC_MV"])),
                    "source": "Tushare daily_basic",
                    "updated_at": datetime.utcnow(),
                }
            )
        return _clean_frame(rows, required=["code", "trade_date"])

    def fetch_stk_factor(self, trade_date: Any) -> pd.DataFrame:
        frame = self._call_api("stk_factor", trade_date=_trade_date_arg(trade_date), fields=self.STK_FACTOR_FIELDS)
        rows = []
        for item in _records(frame):
            row = _base_dated_row(item, "Tushare stk_factor")
            if not row:
                continue
            row.update(
                {
                    "macd": safe_float(first_present(item, ["macd", "MACD"])),
                    "kdj_k": safe_float(first_present(item, ["kdj_k", "KDJ_K"])),
                    "kdj_d": safe_float(first_present(item, ["kdj_d", "KDJ_D"])),
                    "kdj_j": safe_float(first_present(item, ["kdj_j", "KDJ_J"])),
                    "rsi_6": safe_float(first_present(item, ["rsi_6", "RSI_6"])),
                    "rsi_12": safe_float(first_present(item, ["rsi_12", "RSI_12"])),
                    "rsi_24": safe_float(first_present(item, ["rsi_24", "RSI_24"])),
                    "boll_upper": safe_float(first_present(item, ["boll_upper", "BOLL_UPPER"])),
                    "boll_mid": safe_float(first_present(item, ["boll_mid", "BOLL_MID"])),
                    "boll_lower": safe_float(first_present(item, ["boll_lower", "BOLL_LOWER"])),
                    "cci": safe_float(first_present(item, ["cci", "CCI"])),
                }
            )
            rows.append(row)
        return _clean_frame(rows, required=["code", "trade_date"])

    def fetch_moneyflow(self, trade_date: Any) -> pd.DataFrame:
        frame = self._call_api("moneyflow", trade_date=_trade_date_arg(trade_date), fields=self.MONEYFLOW_FIELDS)
        rows = []
        for item in _records(frame):
            row = _base_dated_row(item, "Tushare moneyflow")
            if not row:
                continue
            for field in [
                "buy_sm_amount",
                "sell_sm_amount",
                "buy_md_amount",
                "sell_md_amount",
                "buy_lg_amount",
                "sell_lg_amount",
                "buy_elg_amount",
                "sell_elg_amount",
                "net_mf_amount",
            ]:
                row[field] = _ten_thousand_unit(first_present(item, [field, field.upper()]))
            row["main_net_amount"] = _sum_optional(
                row.get("buy_lg_amount"),
                row.get("buy_elg_amount"),
                -(row.get("sell_lg_amount") or 0),
                -(row.get("sell_elg_amount") or 0),
            )
            rows.append(row)
        return _clean_frame(rows, required=["code", "trade_date"])

    def fetch_limit_list_d(self, trade_date: Any) -> pd.DataFrame:
        frame = self._call_api("limit_list_d", trade_date=_trade_date_arg(trade_date), fields=self.LIMIT_LIST_FIELDS)
        rows = []
        for item in _records(frame):
            row = _base_dated_row(item, "Tushare limit_list_d")
            if not row:
                continue
            row.update(
                {
                    "name": first_present(item, ["name", "NAME"]) or row["code"],
                    "close": safe_float(first_present(item, ["close", "CLOSE"])),
                    "pct_chg": safe_float(first_present(item, ["pct_chg", "PCT_CHG"])),
                    "limit": first_present(item, ["limit", "LIMIT"]),
                    "up_stat": first_present(item, ["up_stat", "UP_STAT"]),
                    "fd_amount": safe_float(first_present(item, ["fd_amount", "FD_AMOUNT"])),
                    "first_time": first_present(item, ["first_time", "FIRST_TIME"]),
                    "last_time": first_present(item, ["last_time", "LAST_TIME"]),
                    "open_times": _safe_int(first_present(item, ["open_times", "OPEN_TIMES"])),
                }
            )
            rows.append(row)
        return _clean_frame(rows, required=["code", "trade_date"])

    def fetch_cyq_perf_for_codes(self, codes: List[str], trade_date: Any, limit: int = 0) -> pd.DataFrame:
        rows = []
        errors = []
        for code in _limited_codes(codes, limit):
            try:
                frame = self._call_api(
                    "cyq_perf",
                    ts_code=code,
                    trade_date=_trade_date_arg(trade_date),
                    fields=self.CYQ_PERF_FIELDS,
                )
            except Exception as exc:
                errors.append(f"{code}: {exc}")
                self._sleep_between_codes()
                continue
            for item in _records(frame):
                row = _base_dated_row(item, "Tushare cyq_perf")
                if not row:
                    continue
                for field in [
                    "his_low",
                    "his_high",
                    "cost_5pct",
                    "cost_15pct",
                    "cost_50pct",
                    "cost_85pct",
                    "cost_95pct",
                    "weight_avg",
                    "winner_rate",
                ]:
                    row[field] = safe_float(first_present(item, [field, field.upper()]))
                rows.append(row)
            self._sleep_between_codes()
        if not rows and errors:
            raise SourceUnavailable(errors[0])
        return _clean_frame(rows, required=["code", "trade_date"])

    def fetch_cyq_chips_for_codes(self, codes: List[str], trade_date: Any, limit: int = 0) -> pd.DataFrame:
        rows = []
        errors = []
        for code in _limited_codes(codes, limit):
            try:
                frame = self._call_api(
                    "cyq_chips",
                    ts_code=code,
                    trade_date=_trade_date_arg(trade_date),
                    fields=self.CYQ_CHIPS_FIELDS,
                )
            except Exception as exc:
                errors.append(f"{code}: {exc}")
                self._sleep_between_codes()
                continue
            for item in _records(frame):
                row = _base_dated_row(item, "Tushare cyq_chips")
                if not row:
                    continue
                row.update(
                    {
                        "price": safe_float(first_present(item, ["price", "PRICE"])),
                        "percent": safe_float(first_present(item, ["percent", "PERCENT"])),
                    }
                )
                rows.append(row)
            self._sleep_between_codes()
        if not rows and errors:
            raise SourceUnavailable(errors[0])
        return _clean_frame(rows, required=["code", "trade_date", "price"])

    def fetch_ths_member_for_codes(self, codes: List[str], limit: int = 0) -> pd.DataFrame:
        rows = []
        errors = []
        for requested_code in _limited_codes(codes, limit):
            try:
                frame = self._call_api("ths_member", con_code=requested_code, fields=self.THS_MEMBER_FIELDS)
            except Exception as exc:
                errors.append(f"{requested_code}: {exc}")
                self._sleep_between_codes()
                continue
            for item in _records(frame):
                stock_code = normalize_a_share_code(
                    first_present(item, ["con_code", "CON_CODE", "code", "stock_code", "CODE", "STOCK_CODE"])
                )
                if not stock_code:
                    continue
                ths_code = first_present(item, ["ts_code", "TS_CODE"])
                rows.append(
                    {
                        "code": stock_code,
                        "name": first_present(item, ["con_name", "CON_NAME", "name", "NAME"]) or stock_code,
                        "con_code": ths_code,
                        "con_name": first_present(item, ["name", "NAME"]) or ths_code,
                        "weight": safe_float(first_present(item, ["weight", "WEIGHT"])),
                        "in_date": _normalize_trade_date(first_present(item, ["in_date", "IN_DATE"])),
                        "out_date": _normalize_trade_date(first_present(item, ["out_date", "OUT_DATE"])),
                        "is_new": first_present(item, ["is_new", "IS_NEW"]),
                        "source": "Tushare ths_member",
                        "updated_at": datetime.utcnow(),
                    }
                )
            self._sleep_between_codes()
        if not rows and errors:
            raise SourceUnavailable(errors[0])
        return _clean_frame(rows, required=["code", "con_code"])

    def fetch_top_list(self, trade_date: Any) -> pd.DataFrame:
        frame = self._call_api("top_list", trade_date=_trade_date_arg(trade_date), fields=self.TOP_LIST_FIELDS)
        rows = []
        for item in _records(frame):
            row = _base_dated_row(item, "Tushare top_list")
            if not row:
                continue
            row.update(
                {
                    "name": first_present(item, ["name", "NAME"]) or row["code"],
                    "close": safe_float(first_present(item, ["close", "CLOSE"])),
                    "pct_change": safe_float(first_present(item, ["pct_change", "PCT_CHANGE"])),
                    "turnover_rate": safe_float(first_present(item, ["turnover_rate", "TURNOVER_RATE"])),
                    "amount": safe_float(first_present(item, ["amount", "AMOUNT"])),
                    "l_sell": safe_float(first_present(item, ["l_sell", "L_SELL"])),
                    "l_buy": safe_float(first_present(item, ["l_buy", "L_BUY"])),
                    "l_amount": safe_float(first_present(item, ["l_amount", "L_AMOUNT"])),
                    "net_amount": safe_float(first_present(item, ["net_amount", "NET_AMOUNT"])),
                    "net_rate": safe_float(first_present(item, ["net_rate", "NET_RATE"])),
                    "amount_rate": safe_float(first_present(item, ["amount_rate", "AMOUNT_RATE"])),
                    "float_values": safe_float(first_present(item, ["float_values", "FLOAT_VALUES"])),
                    "reason": first_present(item, ["reason", "REASON"]) or "",
                }
            )
            rows.append(row)
        return _clean_frame(rows, required=["code", "trade_date"])

    def fetch_top_inst(self, trade_date: Any) -> pd.DataFrame:
        frame = self._call_api("top_inst", trade_date=_trade_date_arg(trade_date), fields=self.TOP_INST_FIELDS)
        rows = []
        for item in _records(frame):
            row = _base_dated_row(item, "Tushare top_inst")
            if not row:
                continue
            row.update(
                {
                    "exalter": first_present(item, ["exalter", "EXALTER"]) or "",
                    "buy": safe_float(first_present(item, ["buy", "BUY"])),
                    "buy_rate": safe_float(first_present(item, ["buy_rate", "BUY_RATE"])),
                    "sell": safe_float(first_present(item, ["sell", "SELL"])),
                    "sell_rate": safe_float(first_present(item, ["sell_rate", "SELL_RATE"])),
                    "net_buy": safe_float(first_present(item, ["net_buy", "NET_BUY"])),
                }
            )
            rows.append(row)
        return _clean_frame(rows, required=["code", "trade_date"])

    def fetch_hm_detail(self, trade_date: Any) -> pd.DataFrame:
        frame = self._call_api("hm_detail", trade_date=_trade_date_arg(trade_date), fields=self.HM_DETAIL_FIELDS)
        rows = []
        for item in _records(frame):
            row = _base_dated_row(item, "Tushare hm_detail")
            if not row:
                continue
            row.update(
                {
                    "name": first_present(item, ["ts_name", "TS_NAME", "name", "NAME"]) or row["code"],
                    "hm_name": first_present(item, ["hm_name", "HM_NAME", "name", "NAME"]) or "",
                    "buy_amount": safe_float(first_present(item, ["buy_amount", "BUY_AMOUNT"])),
                    "sell_amount": safe_float(first_present(item, ["sell_amount", "SELL_AMOUNT"])),
                    "net_amount": safe_float(first_present(item, ["net_amount", "NET_AMOUNT"])),
                }
            )
            rows.append(row)
        return _clean_frame(rows, required=["code", "trade_date"])

    def fetch_index_daily(self, index_codes: List[str], trade_date: Any) -> pd.DataFrame:
        rows = []
        errors = []
        for index_code in index_codes:
            try:
                frame = self._call_api(
                    "index_daily",
                    ts_code=index_code,
                    trade_date=_trade_date_arg(trade_date),
                    fields=self.INDEX_DAILY_FIELDS,
                )
            except Exception as exc:
                errors.append(f"{index_code}: {exc}")
                self._sleep_between_codes()
                continue
            for item in _records(frame):
                code = first_present(item, ["ts_code", "TS_CODE", "index_code", "INDEX_CODE"])
                day = _normalize_trade_date(first_present(item, ["trade_date", "TRADE_DATE"]))
                if not code or not day:
                    continue
                rows.append(
                    {
                        "index_code": str(code),
                        "trade_date": day,
                        "open": safe_float(first_present(item, ["open", "OPEN"])),
                        "high": safe_float(first_present(item, ["high", "HIGH"])),
                        "low": safe_float(first_present(item, ["low", "LOW"])),
                        "close": safe_float(first_present(item, ["close", "CLOSE"])),
                        "pre_close": safe_float(first_present(item, ["pre_close", "PRE_CLOSE"])),
                        "change": safe_float(first_present(item, ["change", "CHANGE"])),
                        "pct_chg": safe_float(first_present(item, ["pct_chg", "PCT_CHG"])),
                        "volume": safe_float(first_present(item, ["vol", "VOL", "volume", "VOLUME"])),
                        "amount": _normalize_tushare_amount(
                            first_present(item, ["amount", "AMOUNT"]),
                            amount_unit="thousand_yuan",
                        ),
                        "source": "Tushare index_daily",
                        "updated_at": datetime.utcnow(),
                    }
                )
            self._sleep_between_codes()
        if not rows and errors:
            raise SourceUnavailable(errors[0])
        return _clean_frame(rows, required=["index_code", "trade_date"])

    def _call_api(self, api_name: str, **params: Any) -> pd.DataFrame:
        _, pro = self.client
        method = getattr(pro, api_name, None)
        if callable(method):
            return method(**params)
        query = getattr(pro, "query", None)
        if callable(query):
            return query(api_name, **params)
        raise SourceUnavailable(f"当前 Tushare 中转未提供 {api_name} 接口。")

    def _sleep_between_codes(self) -> None:
        if self._loop_delay > 0:
            time.sleep(self._loop_delay)


def _trade_date_arg(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10].replace("-", "")
    return text


def _date_from_arg(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return date.fromisoformat(text[:10])
    if len(text) == 8 and text.isdigit():
        return date.fromisoformat(f"{text[:4]}-{text[4:6]}-{text[6:]}")
    return date.fromisoformat(text)


def _date_span(start: date, end: date) -> List[date]:
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def _records(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return frame.to_dict("records")


def _base_dated_row(item: Dict[str, Any], source: str) -> Optional[Dict[str, Any]]:
    code = normalize_a_share_code(first_present(item, ["ts_code", "TS_CODE", "code", "CODE"]))
    trade_date = _normalize_trade_date(first_present(item, ["trade_date", "TRADE_DATE"]))
    if not code or not trade_date:
        return None
    return {"code": code, "trade_date": trade_date, "source": source, "updated_at": datetime.utcnow()}


def _clean_frame(rows: List[Dict[str, Any]], required: List[str]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    clean = []
    for row in rows:
        if all(row.get(key) not in (None, "") for key in required):
            clean.append(row)
    return pd.DataFrame(clean)


def _ten_thousand_unit(value: Any) -> Optional[float]:
    number = safe_float(value)
    if number is None:
        return None
    return number * 10000


def _sum_optional(*values: Optional[float]) -> Optional[float]:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return float(sum(present))


def _safe_int(value: Any) -> Optional[int]:
    number = safe_float(value)
    if number is None:
        return None
    return int(number)


def _scaled_float(value: Any, scale: float) -> Optional[float]:
    number = safe_float(value)
    if number is None:
        return None
    return round(number * scale, 6)


def _hands_to_shares(value: Any) -> Optional[float]:
    number = safe_float(value)
    if number is None:
        return None
    return number * 100


def _limited_codes(codes: List[str], limit: int) -> List[str]:
    if limit and limit > 0:
        return codes[:limit]
    return codes
