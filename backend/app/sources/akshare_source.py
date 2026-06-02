from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from backend.app.services.market_utils import normalize_a_share_code, safe_float
from backend.app.sources.base import SourceUnavailable, first_present


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class AkShareSource:
    sina_name = "AkShare 新浪"
    tencent_name = "AkShare 腾讯"

    def __init__(self) -> None:
        self._ak = None

    @property
    def ak(self) -> Any:
        if self._ak is None:
            import akshare as ak  # type: ignore

            self._ak = ak
        return self._ak

    def fetch_sina_snapshot(self, include_bj: bool = False, exclude_star: bool = False) -> pd.DataFrame:
        if not hasattr(self.ak, "stock_zh_a_spot"):
            raise SourceUnavailable("当前 AkShare 未提供 stock_zh_a_spot 新浪快照接口。")
        frame = self.ak.stock_zh_a_spot()
        return self._normalize_snapshot(frame, self.sina_name, include_bj, exclude_star)

    def fetch_tencent_snapshot(self, include_bj: bool = False, exclude_star: bool = False) -> pd.DataFrame:
        func_name = None
        for candidate in ("stock_zh_a_spot_tx", "stock_zh_a_spot_qq", "stock_zh_a_spot_tencent"):
            if hasattr(self.ak, candidate):
                func_name = candidate
                break
        if not func_name:
            version = getattr(self.ak, "__version__", "unknown")
            raise SourceUnavailable(
                f"当前 AkShare {version} 未暴露可用的腾讯 A 股快照接口。"
            )
        frame = getattr(self.ak, func_name)()
        return self._normalize_snapshot(frame, self.tencent_name, include_bj, exclude_star)

    def _normalize_snapshot(
        self,
        frame: pd.DataFrame,
        source: str,
        include_bj: bool,
        exclude_star: bool,
    ) -> pd.DataFrame:
        if frame is None or frame.empty:
            raise SourceUnavailable("快照接口返回空数据。")
        rows: List[Dict[str, Any]] = []
        snapshot_date = _shanghai_today_iso()
        for item in frame.to_dict("records"):
            code = normalize_a_share_code(
                first_present(item, ["代码", "code", "symbol", "证券代码"]),
                include_bj=include_bj,
                exclude_star=exclude_star,
            )
            if not code:
                continue
            latest = safe_float(first_present(item, ["最新价", "trade", "price", "最新"]))
            if latest is None:
                latest = safe_float(first_present(item, ["收盘价", "close"]))
            amount = safe_float(first_present(item, ["成交额", "amount", "成交金额"]))
            volume = safe_float(first_present(item, ["成交量", "volume"]))
            float_mv = safe_float(first_present(item, ["流通市值", "nmc", "流通市值(元)"]))
            rows.append(
                {
                    "code": code,
                    "date": snapshot_date,
                    "name": first_present(item, ["名称", "name", "股票名称"]) or code,
                    "latest_price": latest,
                    "pct_chg": safe_float(first_present(item, ["涨跌幅", "changepercent", "涨幅", "change_pct"])),
                    "high": safe_float(first_present(item, ["最高", "high", "最高价"])),
                    "low": safe_float(first_present(item, ["最低", "low", "最低价"])),
                    "volume": volume,
                    "amount": amount,
                    "turnover_rate": safe_float(
                        first_present(item, ["换手率", "turnoverratio", "turnover_rate"])
                    ),
                    "float_market_value": float_mv,
                    "source": source,
                    "updated_at": datetime.utcnow(),
                }
            )
        return pd.DataFrame(rows)


def _shanghai_today_iso() -> str:
    return datetime.now(SHANGHAI_TZ).date().isoformat()
