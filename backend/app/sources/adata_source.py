from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from backend.app.services.market_utils import normalize_a_share_code, safe_float
from backend.app.sources.base import SourceUnavailable, first_present


class ADataSource:
    name = "AData"

    def __init__(self) -> None:
        self._adata = None

    @property
    def adata(self) -> Any:
        if self._adata is None:
            import adata  # type: ignore

            self._adata = adata
        return self._adata

    def available(self) -> bool:
        try:
            _ = self.adata
            return True
        except Exception:
            return False

    def fetch_stock_basics(self, include_bj: bool = False, exclude_star: bool = False) -> pd.DataFrame:
        from adata.stock.cache import get_code_csv_path  # type: ignore

        frame = pd.read_csv(get_code_csv_path())
        if frame is None or frame.empty:
            raise SourceUnavailable("AData 本地股票基础信息缓存为空。")
        rows: List[Dict[str, Any]] = []
        for item in frame.to_dict("records"):
            raw_code = first_present(item, ["stock_code", "code", "代码"])
            if raw_code is not None:
                raw_code = str(raw_code).split(".")[0].zfill(6)
            code = normalize_a_share_code(
                raw_code,
                include_bj=include_bj,
                exclude_star=exclude_star,
            )
            if not code:
                continue
            raw_date = first_present(item, ["list_date", "list_date2", "上市日期"])
            if pd.isna(raw_date):
                raw_date = None
            rows.append(
                {
                    "code": code,
                    "name": str(first_present(item, ["short_name", "name", "股票简称"]) or code).replace(" ", ""),
                    "exchange": code.split(".")[1],
                    "list_date": str(raw_date)[:10] if raw_date else None,
                    "source": self.name,
                    "is_st": False,
                    "suspended": False,
                    "updated_at": datetime.utcnow(),
                }
            )
        return pd.DataFrame(rows)

    def fetch_snapshot(
        self,
        include_bj: bool = False,
        exclude_star: bool = False,
        code_list: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        market = getattr(self.adata.stock, "market", None)
        if market is None or not hasattr(market, "list_market_current"):
            raise SourceUnavailable("当前 AData 版本未提供 list_market_current 快照接口。")
        if not code_list:
            raise SourceUnavailable("AData 快照需要本地股票池代码列表。")
        frame = market.list_market_current(code_list=code_list)
        if frame is None or frame.empty:
            raise SourceUnavailable("AData 快照返回空数据。")
        rows: List[Dict[str, Any]] = []
        for item in frame.to_dict("records"):
            code = normalize_a_share_code(
                first_present(item, ["stock_code", "code", "代码"]),
                include_bj=include_bj,
                exclude_star=exclude_star,
            )
            if not code:
                continue
            rows.append(
                {
                    "code": code,
                    "date": date.today().isoformat(),
                    "name": first_present(item, ["short_name", "name", "股票简称"]) or code,
                    "latest_price": safe_float(first_present(item, ["price", "close", "最新价"])),
                    "pct_chg": safe_float(first_present(item, ["change_pct", "涨跌幅"])),
                    "high": safe_float(first_present(item, ["high", "最高"])),
                    "low": safe_float(first_present(item, ["low", "最低"])),
                    "volume": safe_float(first_present(item, ["volume", "成交量"])),
                    "amount": safe_float(first_present(item, ["amount", "成交额"])),
                    "turnover_rate": safe_float(first_present(item, ["turnover", "turnover_rate", "换手率"])),
                    "float_market_value": None,
                    "source": self.name,
                    "updated_at": datetime.utcnow(),
                }
            )
        return pd.DataFrame(rows)

    def fetch_history(self, code: str, start_date: date, end_date: date) -> pd.DataFrame:
        raise SourceUnavailable(
            "当前 AData 2.9.5 历史行情接口内部使用 EM 源，已按项目约束跳过。"
        )

    def fetch_float_shares(self, code: str) -> pd.DataFrame:
        info = getattr(self.adata.stock, "info", None)
        if info is None or not hasattr(info, "get_stock_shares"):
            raise SourceUnavailable("当前 AData 版本未提供股本接口。")
        raise SourceUnavailable("AData 股本接口内部使用 EM 源，已按项目约束跳过。")
