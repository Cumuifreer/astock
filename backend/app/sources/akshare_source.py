from __future__ import annotations

import math
import random
import re
import time
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from backend.app.config import settings
from backend.app.services.market_utils import normalize_a_share_code, safe_float
from backend.app.sources.base import SourceUnavailable, first_present


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class AkShareSource:
    sina_name = "AkShare 新浪"

    def __init__(self) -> None:
        self._ak = None

    @property
    def ak(self) -> Any:
        if self._ak is None:
            import akshare as ak  # type: ignore

            self._ak = ak
        return self._ak

    def fetch_sina_snapshot(
        self,
        include_bj: bool = False,
        exclude_star: bool = False,
        session: Optional[requests.Session] = None,
        progress: Optional[Callable[[int, int, int], None]] = None,
    ) -> pd.DataFrame:
        """Fetch Sina's paginated A-share snapshot with bounded, polite requests.

        AkShare's public helper downloads every page as fast as possible and drops
        several useful raw fields.  We keep its endpoint definitions and decoder,
        while controlling page pacing, per-request timeouts and the overall deadline.
        """
        try:
            from akshare.stock import stock_zh_a_sina as sina  # type: ignore
        except Exception as exc:  # pragma: no cover - import failure is environment-specific
            raise SourceUnavailable(f"当前 AkShare 未提供新浪 A 股快照模块：{exc}") from exc

        required = (
            "zh_sina_a_stock_url",
            "zh_sina_a_stock_count_url",
            "zh_sina_a_stock_payload",
            "demjson",
        )
        if any(not hasattr(sina, name) for name in required):
            raise SourceUnavailable("当前 AkShare 版本的新浪快照接口结构不兼容。")

        owned_session = session is None
        client = session or requests.Session()
        client.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
                ),
                "Referer": "https://finance.sina.com.cn/",
            }
        )
        deadline = time.monotonic() + max(1, settings.sina_total_timeout_seconds)
        rows: List[Dict[str, Any]] = []
        try:
            count_response = client.get(
                sina.zh_sina_a_stock_count_url,
                timeout=settings.sina_request_timeout_seconds,
            )
            count_response.raise_for_status()
            count_match = re.search(r"\d+", count_response.text)
            if not count_match:
                raise SourceUnavailable("新浪快照未返回有效股票数量。")
            expected_count = int(count_match.group())
            page_size = max(1, int(sina.zh_sina_a_stock_payload.get("num", 80)))
            page_count = max(1, math.ceil(expected_count / page_size))
            if progress is not None:
                progress(0, page_count, 0)

            for page in range(1, page_count + 1):
                if time.monotonic() >= deadline:
                    raise SourceUnavailable(
                        f"新浪快照超过 {settings.sina_total_timeout_seconds} 秒总时限，已停止翻页。"
                    )
                payload = dict(sina.zh_sina_a_stock_payload)
                payload["page"] = str(page)
                response = client.get(
                    sina.zh_sina_a_stock_url,
                    params=payload,
                    timeout=settings.sina_request_timeout_seconds,
                )
                response.raise_for_status()
                page_rows = sina.demjson.decode(response.text)
                if not isinstance(page_rows, list):
                    raise SourceUnavailable(f"新浪快照第 {page} 页格式异常。")
                rows.extend(item for item in page_rows if isinstance(item, dict))
                if progress is not None:
                    progress(page, page_count, len(rows))
                if page < page_count:
                    delay = random.uniform(settings.sina_page_min_delay, settings.sina_page_max_delay)
                    if time.monotonic() + delay >= deadline:
                        raise SourceUnavailable(
                            f"新浪快照超过 {settings.sina_total_timeout_seconds} 秒总时限，已停止翻页。"
                        )
                    time.sleep(delay)
        except SourceUnavailable:
            raise
        except Exception as exc:
            raise SourceUnavailable(f"新浪快照请求失败：{exc}") from exc
        finally:
            if owned_session:
                client.close()

        minimum_rows = max(1, int(expected_count * 0.9))
        if len(rows) < minimum_rows:
            raise SourceUnavailable(f"新浪快照仅返回 {len(rows)}/{expected_count} 行，拒绝写入不完整快照。")
        frame = self._normalize_snapshot(
            pd.DataFrame(rows),
            self.sina_name,
            include_bj,
            exclude_star,
            float_market_value_scale=10_000,
        )
        if frame.empty or frame["code"].duplicated().any():
            raise SourceUnavailable("新浪快照代码为空或包含重复行，拒绝写入。")
        priced_ratio = float(frame["latest_price"].notna().mean())
        if priced_ratio < 0.8:
            raise SourceUnavailable(f"新浪快照有效价格覆盖率仅 {priced_ratio:.1%}，拒绝写入。")
        return frame

    def _normalize_snapshot(
        self,
        frame: pd.DataFrame,
        source: str,
        include_bj: bool,
        exclude_star: bool,
        float_market_value_scale: float = 1.0,
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
            if float_mv is not None:
                float_mv *= float_market_value_scale
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
