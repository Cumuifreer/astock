from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from backend.app.db import Database
from backend.app.services.market_utils import safe_float, to_sina_chart_symbol
from backend.app.services.strategy_service import normalize_strategy_config


def compute_amplitude(
    high: Optional[float],
    low: Optional[float],
    prev_close: Optional[float],
) -> Optional[float]:
    high_value = safe_float(high)
    low_value = safe_float(low)
    prev_value = safe_float(prev_close)
    if high_value is None or low_value is None or prev_value is None or prev_value <= 0:
        return None
    return round((high_value - low_value) / prev_value, 6)


def compute_rps_scores(
    closes: pd.DataFrame,
    windows: Sequence[int] = (20, 60, 120),
) -> Dict[str, Dict[str, Optional[float]]]:
    if closes.empty:
        return {}
    frame = closes.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["code", "date", "close"]).sort_values(["code", "date"])
    scores: Dict[str, Dict[str, Optional[float]]] = {}
    for window in windows:
        returns: Dict[str, float] = {}
        for code, group in frame.groupby("code"):
            clean = group.dropna(subset=["close"])
            if len(clean) < 2:
                continue
            start_index = max(0, len(clean) - window - 1)
            start = float(clean.iloc[start_index]["close"])
            end = float(clean.iloc[-1]["close"])
            if start > 0:
                returns[str(code)] = (end - start) / start
        if not returns:
            continue
        ranked = pd.Series(returns).rank(pct=True) * 100
        for code, value in ranked.items():
            scores.setdefault(str(code), {})[f"rps{window}"] = round(float(value), 2)
    return scores


def apply_strategy_filters(
    rows: pd.DataFrame,
    config: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Optional[str]]:
    strategy = normalize_strategy_config(config)
    working = rows.copy()
    funnel: List[Dict[str, Any]] = []

    def mark(step_name: str, before: int, after_frame: pd.DataFrame, note: str = "") -> None:
        funnel.append(
            {
                "step_name": step_name,
                "before_count": int(before),
                "after_count": int(len(after_frame)),
                "removed_count": int(before - len(after_frame)),
                "note": note,
            }
        )

    before = len(working)
    working = working[(working.get("is_st", False) != True) & (working.get("suspended", False) != True)]
    mark("可交易股票", before, working, "排除 ST 与停牌")

    working = _numeric_filter(working, "latest_price", strategy["min_price"], None, "最低股价", funnel)
    working = _numeric_filter(working, "amount", strategy["min_amount"], None, "成交额", funnel)

    min_float = strategy.get("min_float_market_value")
    max_float = strategy.get("max_float_market_value")
    if min_float is not None or max_float is not None:
        before = len(working)
        series = pd.to_numeric(working.get("float_market_value"), errors="coerce")
        mask = pd.Series(True, index=working.index)
        if min_float is not None:
            mask &= series >= float(min_float)
        if max_float is not None:
            mask &= series <= float(max_float)
        if strategy.get("missing_float_market_value_policy") == "allow":
            mask |= series.isna()
        working = working[mask]
        mark("流通市值", before, working, "缺失时按策略配置降级")

    if strategy.get("trend_filter") == "ma_short_above_long":
        before = len(working)
        working = working[
            pd.to_numeric(working.get("ma_short"), errors="coerce")
            > pd.to_numeric(working.get("ma_long"), errors="coerce")
        ]
        mark("趋势过滤", before, working, "短期均线在长期均线上方")

    rps_window = int(strategy.get("rps_window") or 20)
    rps_key = f"rps{rps_window}"
    min_rps = strategy.get(f"min_{rps_key}") or strategy.get("min_rps20")
    if min_rps is not None:
        working = _numeric_filter(working, rps_key, float(min_rps), None, f"RPS{rps_window}", funnel)

    min_turnover = strategy.get("min_turnover")
    max_turnover = strategy.get("max_turnover")
    if min_turnover is not None or max_turnover is not None:
        before = len(working)
        series = pd.to_numeric(working.get("turnover_rate"), errors="coerce")
        mask = pd.Series(True, index=working.index)
        if min_turnover is not None:
            mask &= series >= float(min_turnover)
        if max_turnover is not None:
            mask &= series <= float(max_turnover)
        if strategy.get("missing_turnover_policy") == "allow":
            mask |= series.isna()
        working = working[mask]
        mark("换手率", before, working, "缺失时按策略配置处理")

    working = _numeric_filter(
        working,
        "pct_chg",
        strategy.get("min_pct_chg"),
        strategy.get("max_pct_chg"),
        "涨跌幅",
        funnel,
    )
    working = _numeric_filter(working, "amplitude", None, strategy.get("max_amplitude"), "振幅", funnel)
    working = _numeric_filter(
        working,
        "volume_ratio",
        strategy.get("volume_ratio_min"),
        None,
        "成交量放大",
        funnel,
    )
    working = _numeric_filter(
        working,
        "ma_distance",
        None,
        strategy.get("max_ma_distance"),
        "均线偏离",
        funnel,
    )

    if working.empty:
        zero_reason = _zero_reason(funnel)
        return [], funnel, zero_reason

    candidate_rows = []
    for _, row in working.iterrows():
        candidate = row.to_dict()
        candidate["signal_type"] = _signal_type(candidate, strategy)
        candidate["signal_score"] = _signal_score(candidate, strategy)
        candidate["reasons"] = _candidate_reasons(candidate, strategy)
        candidate_rows.append(candidate)

    sort_by = strategy.get("sort_by") or "signal_score"
    reverse = sort_by not in {"latest_price", "amplitude"}
    candidate_rows.sort(
        key=lambda item: safe_float(item.get(sort_by)) if safe_float(item.get(sort_by)) is not None else -9999,
        reverse=reverse,
    )
    limit = int(strategy.get("candidate_limit") or 50)
    limited = candidate_rows[:limit]
    funnel.append(
        {
            "step_name": "候选数量",
            "before_count": len(candidate_rows),
            "after_count": len(limited),
            "removed_count": max(0, len(candidate_rows) - len(limited)),
            "note": "按策略排序后截取",
        }
    )
    return limited, funnel, None


def _numeric_filter(
    frame: pd.DataFrame,
    column: str,
    min_value: Optional[float],
    max_value: Optional[float],
    step_name: str,
    funnel: List[Dict[str, Any]],
) -> pd.DataFrame:
    if min_value is None and max_value is None:
        return frame
    before = len(frame)
    series = pd.to_numeric(frame.get(column), errors="coerce")
    mask = pd.Series(True, index=frame.index)
    if min_value is not None:
        mask &= series >= float(min_value)
    if max_value is not None:
        mask &= series <= float(max_value)
    filtered = frame[mask]
    funnel.append(
        {
            "step_name": step_name,
            "before_count": int(before),
            "after_count": int(len(filtered)),
            "removed_count": int(before - len(filtered)),
            "note": "",
        }
    )
    return filtered


def _signal_type(row: Dict[str, Any], strategy: Dict[str, Any]) -> str:
    distance = safe_float(row.get("ma_distance"))
    volume_ratio = safe_float(row.get("volume_ratio")) or 0
    if strategy.get("signal_mode") == "pullback":
        return "左侧回踩"
    if distance is not None and distance <= float(strategy.get("pullback_tolerance") or 0.04):
        return "左侧回踩"
    if volume_ratio >= float(strategy.get("volume_ratio_min") or 1.0):
        return "右侧突破"
    return "趋势观察"


def _signal_score(row: Dict[str, Any], strategy: Dict[str, Any]) -> float:
    rps = safe_float(row.get(f"rps{int(strategy.get('rps_window') or 20)}")) or safe_float(row.get("rps20")) or 0
    volume_ratio = min((safe_float(row.get("volume_ratio")) or 0) * 8, 20)
    trend_bonus = 12 if (safe_float(row.get("ma_short")) or 0) > (safe_float(row.get("ma_long")) or 0) else 0
    turnover = min((safe_float(row.get("turnover_rate")) or 0) * 1.5, 12)
    amplitude_penalty = min((safe_float(row.get("amplitude")) or 0) * 40, 8)
    return round(float(rps) * 0.65 + volume_ratio + trend_bonus + turnover - amplitude_penalty, 2)


def _candidate_reasons(row: Dict[str, Any], strategy: Dict[str, Any]) -> List[str]:
    reasons = []
    amount = safe_float(row.get("amount"))
    if amount is not None:
        reasons.append(f"成交额 {amount / 100_000_000:.2f} 亿")
    rps_key = f"rps{int(strategy.get('rps_window') or 20)}"
    rps = safe_float(row.get(rps_key))
    if rps is not None:
        reasons.append(f"{rps_key.upper()} {rps:.2f}")
    ma_short = safe_float(row.get("ma_short"))
    ma_long = safe_float(row.get("ma_long"))
    if ma_short is not None and ma_long is not None and ma_short > ma_long:
        reasons.append("短期均线强于长期均线")
    turnover = safe_float(row.get("turnover_rate"))
    if turnover is None:
        reasons.append("换手率缺失，按策略降级")
    else:
        reasons.append(f"换手率 {turnover:.2f}%")
    if safe_float(row.get("float_market_value")) is None:
        reasons.append("流通市值缺失，按策略降级")
    return reasons


def _zero_reason(funnel: List[Dict[str, Any]]) -> str:
    if not funnel:
        return "本地仓库暂无可分析行情，请先更新数据。"
    largest = max(funnel, key=lambda item: item.get("removed_count", 0))
    if largest.get("removed_count", 0) <= 0:
        return "没有股票同时满足当前策略，请放宽指标或更新更多历史数据。"
    return f"主要卡在“{largest['step_name']}”：该层过滤掉 {largest['removed_count']} 只股票。"


class AnalysisService:
    def __init__(self, db: Database):
        self.db = db

    def run(self, config: Dict[str, Any]) -> str:
        run_id = f"analysis-{uuid.uuid4().hex[:12]}"
        strategy = normalize_strategy_config(config)
        now = datetime.utcnow()
        self.db.upsert(
            "analysis_runs",
            [
                {
                    "id": run_id,
                    "status": "running",
                    "started_at": now,
                    "finished_at": None,
                    "config_json": json.dumps(strategy, ensure_ascii=False),
                    "summary_json": "{}",
                    "error_message": None,
                }
            ],
            ["id"],
        )
        try:
            rows = self._build_analysis_frame(strategy)
            candidates, funnel, zero_reason = apply_strategy_filters(rows, strategy)
            self._persist_results(run_id, candidates, funnel, zero_reason)
            status = "completed_full"
            summary = {
                "candidate_count": len(candidates),
                "zero_reason": zero_reason,
                "analyzed_count": len(rows),
                "finished_at": datetime.utcnow().isoformat(timespec="seconds"),
            }
            self.db.upsert(
                "analysis_runs",
                [
                    {
                        "id": run_id,
                        "status": status,
                        "started_at": now,
                        "finished_at": datetime.utcnow(),
                        "config_json": json.dumps(strategy, ensure_ascii=False),
                        "summary_json": json.dumps(summary, ensure_ascii=False),
                        "error_message": None,
                    }
                ],
                ["id"],
            )
        except Exception as exc:
            self.db.execute(
                "UPDATE analysis_runs SET status = 'failed', finished_at = ?, error_message = ? WHERE id = ?",
                [datetime.utcnow(), str(exc), run_id],
                write=True,
            )
            raise
        return run_id

    def _build_analysis_frame(self, strategy: Dict[str, Any]) -> pd.DataFrame:
        bars = pd.DataFrame(
            self.db.query(
                """
                SELECT h.*, b.name, b.suspended
                FROM historical_bars h
                LEFT JOIN stock_basic b USING (code)
                WHERE h.date >= current_date - INTERVAL 260 DAY
                ORDER BY h.code, h.date
                """
            )
        )
        if bars.empty:
            return pd.DataFrame()
        snapshots = pd.DataFrame(
            self.db.query(
                """
                SELECT *
                FROM daily_snapshots
                WHERE date = (SELECT MAX(date) FROM daily_snapshots)
                """
            )
        )
        float_values = pd.DataFrame(
            self.db.query(
                """
                SELECT *
                FROM float_market_values
                WHERE date = (SELECT MAX(date) FROM float_market_values)
                """
            )
        )
        rps_scores = compute_rps_scores(bars[["code", "date", "close"]], windows=(20, 60, 120))
        output = []
        for code, group in bars.groupby("code"):
            group = group.sort_values("date")
            latest_bar = group.iloc[-1].to_dict()
            snapshot = _first_record(snapshots, code)
            float_record = _first_record(float_values, code)
            latest_price = safe_float((snapshot or {}).get("latest_price")) or safe_float(latest_bar.get("close"))
            ma_short_window = int(strategy.get("ma_short_window") or 20)
            ma_long_window = int(strategy.get("ma_long_window") or 60)
            closes = pd.to_numeric(group["close"], errors="coerce").dropna()
            volumes = pd.to_numeric(group["volume"], errors="coerce").dropna()
            ma_short = float(closes.tail(ma_short_window).mean()) if len(closes) >= ma_short_window else None
            ma_long = float(closes.tail(ma_long_window).mean()) if len(closes) >= ma_long_window else None
            prev_volume_mean = float(volumes.iloc[:-1].tail(20).mean()) if len(volumes) > 1 else None
            latest_volume = safe_float((snapshot or {}).get("volume")) or safe_float(latest_bar.get("volume"))
            volume_ratio = latest_volume / prev_volume_mean if latest_volume and prev_volume_mean else None
            ma_distance = (
                abs(latest_price - ma_short) / ma_short
                if latest_price is not None and ma_short is not None and ma_short > 0
                else None
            )
            float_mv = (
                safe_float((float_record or {}).get("float_market_value"))
                or safe_float((snapshot or {}).get("float_market_value"))
            )
            output.append(
                {
                    "code": code,
                    "name": (snapshot or {}).get("name") or latest_bar.get("name") or code,
                    "latest_price": latest_price,
                    "pct_chg": safe_float((snapshot or {}).get("pct_chg")) or safe_float(latest_bar.get("pct_chg")),
                    "amount": safe_float((snapshot or {}).get("amount")) or safe_float(latest_bar.get("amount")),
                    "volume": latest_volume,
                    "turnover_rate": safe_float((snapshot or {}).get("turnover_rate"))
                    or safe_float(latest_bar.get("turn")),
                    "amplitude": compute_amplitude(
                        safe_float(latest_bar.get("high")),
                        safe_float(latest_bar.get("low")),
                        safe_float(latest_bar.get("prev_close")),
                    ),
                    "rps20": rps_scores.get(code, {}).get("rps20"),
                    "rps60": rps_scores.get(code, {}).get("rps60"),
                    "rps120": rps_scores.get(code, {}).get("rps120"),
                    "ma_short": ma_short,
                    "ma_long": ma_long,
                    "float_market_value": float_mv,
                    "volume_ratio": volume_ratio,
                    "ma_distance": ma_distance,
                    "is_st": bool(latest_bar.get("is_st")),
                    "suspended": str(latest_bar.get("tradestatus")) == "0" or bool(latest_bar.get("suspended")),
                    "data_sources": {
                        "history": latest_bar.get("source"),
                        "snapshot": (snapshot or {}).get("source"),
                        "float_market_value": (float_record or {}).get("source"),
                    },
                }
            )
        return pd.DataFrame(output)

    def _persist_results(
        self,
        run_id: str,
        candidates: List[Dict[str, Any]],
        funnel: List[Dict[str, Any]],
        zero_reason: Optional[str],
    ) -> None:
        self.db.execute("DELETE FROM candidate_results WHERE run_id = ?", [run_id], write=True)
        self.db.execute("DELETE FROM funnel_stats WHERE run_id = ?", [run_id], write=True)
        now = datetime.utcnow()
        funnel_rows = []
        for index, step in enumerate(funnel):
            funnel_rows.append(
                {
                    "run_id": run_id,
                    "order_index": index,
                    "step_name": step["step_name"],
                    "before_count": step["before_count"],
                    "after_count": step["after_count"],
                    "removed_count": step["removed_count"],
                    "note": step.get("note"),
                }
            )
        self.db.upsert("funnel_stats", funnel_rows, ["run_id", "order_index"])
        candidate_rows = []
        for rank, candidate in enumerate(candidates, start=1):
            code = candidate["code"]
            candidate_rows.append(
                {
                    "run_id": run_id,
                    "rank": rank,
                    "code": code,
                    "name": candidate.get("name"),
                    "latest_price": safe_float(candidate.get("latest_price")),
                    "pct_chg": safe_float(candidate.get("pct_chg")),
                    "amount": safe_float(candidate.get("amount")),
                    "volume": safe_float(candidate.get("volume")),
                    "turnover_rate": safe_float(candidate.get("turnover_rate")),
                    "amplitude": safe_float(candidate.get("amplitude")),
                    "rps20": safe_float(candidate.get("rps20")),
                    "rps60": safe_float(candidate.get("rps60")),
                    "rps120": safe_float(candidate.get("rps120")),
                    "ma_short": safe_float(candidate.get("ma_short")),
                    "ma_long": safe_float(candidate.get("ma_long")),
                    "float_market_value": safe_float(candidate.get("float_market_value")),
                    "signal_type": candidate.get("signal_type"),
                    "signal_score": safe_float(candidate.get("signal_score")),
                    "data_sources": json.dumps(candidate.get("data_sources") or {}, ensure_ascii=False),
                    "reasons_json": json.dumps(candidate.get("reasons") or [], ensure_ascii=False),
                    "chart_url": f"https://finance.sina.com.cn/realstock/company/{to_sina_chart_symbol(code)}/nc.shtml",
                    "metrics_json": json.dumps(_jsonable(candidate), ensure_ascii=False),
                    "created_at": now,
                }
            )
        self.db.upsert("candidate_results", candidate_rows, ["run_id", "code"])


def _first_record(frame: pd.DataFrame, code: str) -> Optional[Dict[str, Any]]:
    if frame.empty or "code" not in frame:
        return None
    found = frame[frame["code"] == code]
    if found.empty:
        return None
    return found.iloc[0].to_dict()


def _jsonable(row: Dict[str, Any]) -> Dict[str, Any]:
    clean = {}
    for key, value in row.items():
        if isinstance(value, (list, dict, str, int, float, bool)) or value is None:
            clean[key] = value
        elif pd.isna(value):
            clean[key] = None
        else:
            clean[key] = str(value)
    return clean
