from __future__ import annotations

import json
import math
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


def compute_platform_breakout_metrics(group: pd.DataFrame, strategy: Dict[str, Any]) -> Dict[str, Any]:
    platform_days = max(5, int(strategy.get("platform_lookback_days") or 20))
    if len(group) < platform_days + 1:
        return {"platform_ready": False}

    clean = group.copy().sort_values("date")
    for column in ["open", "high", "low", "close", "prev_close", "volume", "pct_chg"]:
        clean[column] = pd.to_numeric(clean.get(column), errors="coerce")
    latest = clean.iloc[-1]
    platform = clean.iloc[-platform_days - 1 : -1].dropna(subset=["open", "high", "low", "close", "volume"])
    if len(platform) < platform_days:
        return {"platform_ready": False}

    platform_high = safe_float(platform["high"].max())
    platform_low = safe_float(platform["low"].min())
    platform_range = (
        (platform_high - platform_low) / platform_low
        if platform_high is not None and platform_low is not None and platform_low > 0
        else None
    )
    bullish = platform[platform["close"] > platform["open"]]
    bearish = platform[platform["close"] < platform["open"]]
    bullish_ratio = len(bullish) / len(platform) if len(platform) else None
    bull_avg_volume = safe_float(bullish["volume"].mean()) if not bullish.empty else None
    bear_avg_volume = safe_float(bearish["volume"].mean()) if not bearish.empty else None
    if bull_avg_volume is not None and (bear_avg_volume is None or bear_avg_volume <= 0):
        bull_volume_ratio = float("inf")
    elif bull_avg_volume is not None and bear_avg_volume is not None:
        bull_volume_ratio = bull_avg_volume / bear_avg_volume
    else:
        bull_volume_ratio = None

    latest_volume = safe_float(latest.get("volume"))
    platform_avg_volume = safe_float(platform["volume"].mean())
    breakout_volume_ratio = (
        latest_volume / platform_avg_volume
        if latest_volume is not None and platform_avg_volume is not None and platform_avg_volume > 0
        else None
    )
    open_value = safe_float(latest.get("open"))
    high_value = safe_float(latest.get("high"))
    low_value = safe_float(latest.get("low"))
    close_value = safe_float(latest.get("close"))
    pct_chg = safe_float(latest.get("pct_chg"))
    breakout_bullish = bool(close_value is not None and open_value is not None and close_value > open_value)
    body_strength = None
    if breakout_bullish and high_value is not None and low_value is not None:
        body = close_value - open_value
        shadows = max(0.0, high_value - close_value) + max(0.0, open_value - low_value)
        body_strength = float("inf") if shadows == 0 else body / shadows

    ma_fast, ma_mid, ma_slow = _platform_ma_values(clean["close"])
    prev_fast, prev_mid, prev_slow = _platform_ma_values(clean["close"].iloc[:-1])
    ma_bullish = _ordered_positive(ma_fast, ma_mid, ma_slow)
    ma_rising = (
        ma_bullish
        and prev_fast is not None
        and prev_mid is not None
        and prev_slow is not None
        and ma_fast > prev_fast
        and ma_mid > prev_mid
        and ma_slow > prev_slow
    )
    macd_dif, macd_dea = _macd_values(clean["close"])

    return {
        "platform_ready": True,
        "platform_range": _round_optional(platform_range, 6),
        "platform_bullish_ratio": _round_optional(bullish_ratio, 6),
        "platform_bull_volume_ratio": _round_optional(bull_volume_ratio, 6),
        "platform_breakout_volume_ratio": _round_optional(breakout_volume_ratio, 6),
        "platform_breakout_bullish": breakout_bullish,
        "platform_breakout_pct_chg": pct_chg,
        "platform_body_strength": _round_optional(body_strength, 6),
        "platform_ma_fast": _round_optional(ma_fast, 6),
        "platform_ma_mid": _round_optional(ma_mid, 6),
        "platform_ma_slow": _round_optional(ma_slow, 6),
        "platform_ma_bullish": ma_bullish,
        "platform_ma_rising": bool(ma_rising),
        "macd_dif": _round_optional(macd_dif, 6),
        "macd_dea": _round_optional(macd_dea, 6),
    }


def compute_platform_setup_metrics(group: pd.DataFrame, strategy: Dict[str, Any]) -> Dict[str, Any]:
    platform_days = max(10, int(strategy.get("platform_setup_lookback_days") or 20))
    if len(group) < platform_days:
        return {"platform_setup_ready": False}

    clean = group.copy().sort_values("date")
    for column in ["open", "high", "low", "close", "volume"]:
        clean[column] = pd.to_numeric(clean.get(column), errors="coerce")
    window = clean.iloc[-platform_days:].dropna(subset=["open", "high", "low", "close", "volume"])
    if len(window) < platform_days:
        return {"platform_setup_ready": False}

    latest = clean.iloc[-1]
    close_value = safe_float(latest.get("close"))
    platform_high = safe_float(window["high"].max())
    platform_low = safe_float(window["low"].min())
    platform_range = (
        (platform_high - platform_low) / platform_low
        if platform_high is not None and platform_low is not None and platform_low > 0
        else None
    )
    distance_to_high = (
        max(0.0, (platform_high - close_value) / platform_high)
        if platform_high is not None and close_value is not None and platform_high > 0
        else None
    )

    closes = pd.to_numeric(clean["close"], errors="coerce").dropna()
    recent_gain_5d = None
    if len(closes) >= 6:
        base = safe_float(closes.iloc[-6])
        latest_close = safe_float(closes.iloc[-1])
        if base is not None and latest_close is not None and base > 0:
            recent_gain_5d = (latest_close - base) / base

    recent_volume = safe_float(window["volume"].tail(5).mean())
    platform_avg_volume = safe_float(window["volume"].mean())
    volume_contraction = (
        recent_volume / platform_avg_volume
        if recent_volume is not None and platform_avg_volume is not None and platform_avg_volume > 0
        else None
    )

    bullish = window[window["close"] > window["open"]]
    bearish = window[window["close"] < window["open"]]
    bull_avg_volume = safe_float(bullish["volume"].mean()) if not bullish.empty else None
    bear_avg_volume = safe_float(bearish["volume"].mean()) if not bearish.empty else None
    if bull_avg_volume is not None and (bear_avg_volume is None or bear_avg_volume <= 0):
        bull_volume_ratio = float("inf")
    elif bull_avg_volume is not None and bear_avg_volume is not None:
        bull_volume_ratio = bull_avg_volume / bear_avg_volume
    else:
        bull_volume_ratio = None

    ma_fast, ma_mid, ma_slow = _platform_ma_values(clean["close"])
    prev_fast, _, _ = _platform_ma_values(clean["close"].iloc[:-1])
    ma_values = [value for value in [ma_fast, ma_mid, ma_slow] if value is not None]
    ma_convergence = (
        (max(ma_values) - min(ma_values)) / close_value
        if close_value is not None and close_value > 0 and len(ma_values) == 3
        else None
    )
    ma_turning_up = (
        ma_fast is not None
        and prev_fast is not None
        and close_value is not None
        and ma_fast > prev_fast
        and close_value >= ma_fast
    )
    macd_dif, macd_dea = _macd_values(clean["close"])

    return {
        "platform_setup_ready": True,
        "platform_setup_range": _round_optional(platform_range, 6),
        "platform_setup_distance_to_high": _round_optional(distance_to_high, 6),
        "platform_setup_recent_gain_5d": _round_optional(recent_gain_5d, 6),
        "platform_setup_volume_contraction": _round_optional(volume_contraction, 6),
        "platform_setup_bull_volume_ratio": _round_optional(bull_volume_ratio, 6),
        "platform_setup_ma_convergence": _round_optional(ma_convergence, 6),
        "platform_setup_ma_turning_up": bool(ma_turning_up),
        "platform_setup_ma_fast": _round_optional(ma_fast, 6),
        "platform_setup_ma_mid": _round_optional(ma_mid, 6),
        "platform_setup_ma_slow": _round_optional(ma_slow, 6),
        "macd_dif": _round_optional(macd_dif, 6),
        "macd_dea": _round_optional(macd_dea, 6),
    }


def _platform_ma_values(closes: pd.Series) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    clean = pd.to_numeric(closes, errors="coerce").dropna()
    if len(clean) < 20:
        return None, None, None
    return (
        float(clean.tail(5).mean()),
        float(clean.tail(10).mean()),
        float(clean.tail(20).mean()),
    )


def _ordered_positive(
    fast: Optional[float],
    mid: Optional[float],
    slow: Optional[float],
) -> bool:
    return fast is not None and mid is not None and slow is not None and fast > mid > slow


def _macd_values(closes: pd.Series) -> Tuple[Optional[float], Optional[float]]:
    clean = pd.to_numeric(closes, errors="coerce").dropna()
    if len(clean) < 26:
        return None, None
    ema12 = clean.ewm(span=12, adjust=False).mean()
    ema26 = clean.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    return float(dif.iloc[-1]), float(dea.iloc[-1])


def _round_optional(value: Optional[float], digits: int) -> Optional[float]:
    if value is None:
        return None
    if not math.isfinite(float(value)):
        return 999.0
    return round(float(value), digits)


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

    if strategy.get("analysis_mode") == "score":
        return _rank_candidates(
            working,
            strategy,
            funnel,
            score_mode=True,
        )

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
    if strategy.get("signal_mode") != "platform_setup":
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
    if strategy.get("signal_mode") == "platform_breakout":
        working = _apply_platform_breakout_filters(working, strategy, funnel)
    if strategy.get("signal_mode") == "platform_setup":
        working = _apply_platform_setup_filters(working, strategy, funnel)

    if working.empty:
        zero_reason = _zero_reason(funnel)
        return [], funnel, zero_reason

    return _rank_candidates(working, strategy, funnel)


def _rank_candidates(
    working: pd.DataFrame,
    strategy: Dict[str, Any],
    funnel: List[Dict[str, Any]],
    score_mode: bool = False,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Optional[str]]:
    if working.empty:
        zero_reason = _zero_reason(funnel)
        return [], funnel, zero_reason

    if score_mode:
        funnel.append(
            {
                "step_name": "综合评分",
                "before_count": int(len(working)),
                "after_count": int(len(working)),
                "removed_count": 0,
                "note": "形态、量能、趋势和强弱共同排序",
            }
        )

    candidate_rows = []
    for _, row in working.iterrows():
        candidate = row.to_dict()
        candidate["signal_type"] = _signal_type(candidate, strategy)
        candidate["signal_score"] = _signal_score(candidate, strategy)
        reasons = _candidate_reasons(candidate, strategy)
        if score_mode:
            reasons = ["综合评分：未达标项只影响分数"] + reasons
        candidate["reasons"] = reasons
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


def _apply_platform_breakout_filters(
    frame: pd.DataFrame,
    strategy: Dict[str, Any],
    funnel: List[Dict[str, Any]],
) -> pd.DataFrame:
    working = _bool_filter(frame, "platform_ready", "平台数据", funnel, "需要足够历史 K 线")
    working = _numeric_filter(
        working,
        "platform_range",
        None,
        strategy.get("platform_max_range"),
        "平台振幅",
        funnel,
    )
    working = _numeric_filter(
        working,
        "platform_bullish_ratio",
        strategy.get("platform_min_bullish_ratio"),
        None,
        "阳线占比",
        funnel,
    )
    working = _numeric_filter(
        working,
        "platform_bull_volume_ratio",
        strategy.get("platform_bull_volume_advantage"),
        None,
        "阳线量能",
        funnel,
    )
    working = _numeric_filter(
        working,
        "platform_breakout_volume_ratio",
        strategy.get("platform_breakout_volume_ratio"),
        None,
        "突破量比",
        funnel,
    )
    working = _numeric_filter(
        working,
        "platform_breakout_pct_chg",
        strategy.get("platform_breakout_pct_chg_min"),
        None,
        "突破涨幅",
        funnel,
    )
    working = _bool_filter(working, "platform_breakout_bullish", "突破阳线", funnel, "突破当日为红柱")
    working = _numeric_filter(
        working,
        "platform_body_strength",
        strategy.get("platform_body_strength_min"),
        None,
        "实体强度",
        funnel,
    )
    if strategy.get("platform_ma_trend_enabled"):
        working = _bool_filter(working, "platform_ma_bullish", "MA5/10/20 多头", funnel, "MA5 > MA10 > MA20")
    if strategy.get("platform_ma_rising_required"):
        working = _bool_filter(working, "platform_ma_rising", "均线上升", funnel, "MA5/10/20 均向上")
    if strategy.get("macd_filter_enabled"):
        before = len(working)
        dif = pd.to_numeric(working.get("macd_dif"), errors="coerce")
        dea = pd.to_numeric(working.get("macd_dea"), errors="coerce")
        if strategy.get("macd_position") == "dif_dea_above_zero":
            mask = (dif > 0) & (dea > 0)
            note = "DIF 与 DEA 在 0 轴上方"
        else:
            mask = dif > 0
            note = "DIF 在 0 轴上方"
        working = working[mask]
        funnel.append(
            {
                "step_name": "MACD 位置",
                "before_count": int(before),
                "after_count": int(len(working)),
                "removed_count": int(before - len(working)),
                "note": note,
            }
        )
    return working


def _apply_platform_setup_filters(
    frame: pd.DataFrame,
    strategy: Dict[str, Any],
    funnel: List[Dict[str, Any]],
) -> pd.DataFrame:
    working = _bool_filter(frame, "platform_setup_ready", "平台数据", funnel, "需要足够历史 K 线")
    working = _numeric_filter(
        working,
        "platform_setup_range",
        None,
        strategy.get("platform_setup_max_range"),
        "平台压缩",
        funnel,
    )
    working = _numeric_filter(
        working,
        "platform_setup_distance_to_high",
        None,
        strategy.get("platform_setup_max_distance_to_high"),
        "接近平台上沿",
        funnel,
    )
    working = _numeric_filter(
        working,
        "platform_setup_recent_gain_5d",
        None,
        strategy.get("platform_setup_max_recent_gain_5d"),
        "短线不过热",
        funnel,
    )
    working = _numeric_filter(
        working,
        "platform_setup_volume_contraction",
        None,
        strategy.get("platform_setup_volume_contraction_max"),
        "缩量整理",
        funnel,
    )
    working = _numeric_filter(
        working,
        "platform_setup_bull_volume_ratio",
        strategy.get("platform_setup_bull_volume_advantage"),
        None,
        "阳线量能",
        funnel,
    )
    working = _numeric_filter(
        working,
        "platform_setup_ma_convergence",
        None,
        strategy.get("platform_setup_ma_convergence_max"),
        "均线粘合",
        funnel,
    )
    if strategy.get("platform_setup_require_ma_turning"):
        working = _bool_filter(working, "platform_setup_ma_turning_up", "均线拐头", funnel, "MA5 向上且价格在 MA5 上方")
    macd_mode = strategy.get("platform_setup_macd_mode")
    if macd_mode and macd_mode != "none":
        before = len(working)
        dif = pd.to_numeric(working.get("macd_dif"), errors="coerce")
        dea = pd.to_numeric(working.get("macd_dea"), errors="coerce")
        if macd_mode == "dif_above_zero":
            mask = dif > 0
            note = "DIF 在 0 轴上方"
        else:
            mask = dif > dea
            note = "DIF 强于 DEA"
        working = working[mask]
        funnel.append(
            {
                "step_name": "MACD 转强",
                "before_count": int(before),
                "after_count": int(len(working)),
                "removed_count": int(before - len(working)),
                "note": note,
            }
        )
    return working


def _bool_filter(
    frame: pd.DataFrame,
    column: str,
    step_name: str,
    funnel: List[Dict[str, Any]],
    note: str = "",
) -> pd.DataFrame:
    before = len(frame)
    if column not in frame:
        filtered = frame.iloc[0:0]
    else:
        filtered = frame[frame[column] == True]
    funnel.append(
        {
            "step_name": step_name,
            "before_count": int(before),
            "after_count": int(len(filtered)),
            "removed_count": int(before - len(filtered)),
            "note": note,
        }
    )
    return filtered


def _signal_type(row: Dict[str, Any], strategy: Dict[str, Any]) -> str:
    if strategy.get("signal_mode") == "platform_setup":
        return "平台临界"
    if strategy.get("signal_mode") == "platform_breakout":
        if strategy.get("analysis_mode") == "score":
            return "平台突破观察"
        return "平台突破"
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
    if strategy.get("signal_mode") == "platform_setup":
        setup_range = safe_float(row.get("platform_setup_range"))
        distance_to_high = safe_float(row.get("platform_setup_distance_to_high"))
        recent_gain = safe_float(row.get("platform_setup_recent_gain_5d"))
        volume_contraction = safe_float(row.get("platform_setup_volume_contraction"))
        bull_volume_ratio = safe_float(row.get("platform_setup_bull_volume_ratio"))
        ma_convergence = safe_float(row.get("platform_setup_ma_convergence"))
        max_range = safe_float(strategy.get("platform_setup_max_range")) or 0.1
        max_distance = safe_float(strategy.get("platform_setup_max_distance_to_high")) or 0.035
        max_recent_gain = safe_float(strategy.get("platform_setup_max_recent_gain_5d")) or 0.1
        max_volume_contraction = safe_float(strategy.get("platform_setup_volume_contraction_max")) or 1.05
        min_bull_volume = safe_float(strategy.get("platform_setup_bull_volume_advantage")) or 1.05
        max_ma_convergence = safe_float(strategy.get("platform_setup_ma_convergence_max")) or 0.05
        min_rps = safe_float(strategy.get(f"min_rps{int(strategy.get('rps_window') or 20)}")) or safe_float(
            strategy.get("min_rps20")
        )

        score = float(rps) * 0.5
        if setup_range is not None:
            score += max(0.0, (max_range - setup_range) / max_range) * 14 if setup_range <= max_range else -8
        if distance_to_high is not None:
            score += (
                max(0.0, (max_distance - distance_to_high) / max_distance) * 18
                if distance_to_high <= max_distance
                else -10
            )
        if recent_gain is not None:
            score += 8 if recent_gain <= max_recent_gain else -min((recent_gain - max_recent_gain) * 100, 12)
        if volume_contraction is not None:
            score += (
                max(0.0, (max_volume_contraction - volume_contraction) / max_volume_contraction) * 8
                if volume_contraction <= max_volume_contraction
                else -min((volume_contraction - max_volume_contraction) * 10, 8)
            )
        if bull_volume_ratio is not None:
            score += min(bull_volume_ratio * 6, 12)
        if ma_convergence is not None:
            score += (
                max(0.0, (max_ma_convergence - ma_convergence) / max_ma_convergence) * 8
                if ma_convergence <= max_ma_convergence
                else -6
            )
        if row.get("platform_setup_ma_turning_up"):
            score += 8
        if (safe_float(row.get("macd_dif")) or 0) > (safe_float(row.get("macd_dea")) or 0):
            score += 5
        if setup_range is not None and distance_to_high is not None and setup_range <= max_range and distance_to_high <= max_distance:
            score += 8
        if (
            volume_contraction is not None
            and bull_volume_ratio is not None
            and volume_contraction <= max_volume_contraction
            and bull_volume_ratio >= min_bull_volume
        ):
            score += 5
        if min_rps is not None and recent_gain is not None and rps >= min_rps and recent_gain <= max_recent_gain:
            score += 5
        if ma_convergence is not None and ma_convergence <= max_ma_convergence and row.get("platform_setup_ma_turning_up"):
            score += 5
        return round(max(score, 0), 2)
    if strategy.get("signal_mode") == "platform_breakout":
        platform_range = safe_float(row.get("platform_range"))
        bullish_ratio = safe_float(row.get("platform_bullish_ratio"))
        bull_volume_ratio = safe_float(row.get("platform_bull_volume_ratio"))
        breakout_volume_ratio = safe_float(row.get("platform_breakout_volume_ratio"))
        breakout_pct = safe_float(row.get("platform_breakout_pct_chg"))
        body_strength = safe_float(row.get("platform_body_strength"))

        breakout_volume = min((breakout_volume_ratio or 0) * 7, 24)
        bull_volume = min((bull_volume_ratio or 0) * 7, 14)
        pct_bonus = min(max(breakout_pct or 0, 0) * 1.2, 14)
        trend_bonus = 10 if row.get("platform_ma_bullish") else 0
        macd_bonus = 6 if (safe_float(row.get("macd_dif")) or 0) > 0 else 0
        range_penalty = min((platform_range or 0) * 80, 8)
        score = float(rps) * 0.45 + breakout_volume + bull_volume + pct_bonus + trend_bonus + macd_bonus - range_penalty

        max_range = safe_float(strategy.get("platform_max_range"))
        min_bullish_ratio = safe_float(strategy.get("platform_min_bullish_ratio"))
        min_bull_volume = safe_float(strategy.get("platform_bull_volume_advantage"))
        min_breakout_volume = safe_float(strategy.get("platform_breakout_volume_ratio"))
        min_breakout_pct = safe_float(strategy.get("platform_breakout_pct_chg_min"))
        min_body_strength = safe_float(strategy.get("platform_body_strength_min"))
        min_rps = safe_float(strategy.get(f"min_rps{int(strategy.get('rps_window') or 20)}")) or safe_float(
            strategy.get("min_rps20")
        )

        if max_range is not None and platform_range is not None:
            score += 7 if platform_range <= max_range else -min((platform_range - max_range) * 70, 8)
        if min_breakout_volume is not None and breakout_volume_ratio is not None:
            if breakout_volume_ratio >= min_breakout_volume:
                score += 8
            elif breakout_volume_ratio >= min_breakout_volume * 0.7:
                score += 3
        if (
            min_bullish_ratio is not None
            and min_bull_volume is not None
            and bullish_ratio is not None
            and bull_volume_ratio is not None
            and bullish_ratio >= min_bullish_ratio
            and bull_volume_ratio >= min_bull_volume
        ):
            score += 5
        if (
            min_breakout_pct is not None
            and min_body_strength is not None
            and breakout_pct is not None
            and body_strength is not None
            and breakout_pct >= min_breakout_pct
            and body_strength >= min_body_strength
            and row.get("platform_breakout_bullish")
        ):
            score += 5
        if min_rps is not None and rps >= min_rps and row.get("platform_ma_bullish"):
            score += 6
        if row.get("platform_ma_rising") and macd_bonus > 0:
            score += 4
        return round(max(score, 0), 2)
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
    if strategy.get("signal_mode") == "platform_setup":
        setup_range = safe_float(row.get("platform_setup_range"))
        if setup_range is not None:
            reasons.append(f"平台振幅 {setup_range * 100:.2f}%")
        distance_to_high = safe_float(row.get("platform_setup_distance_to_high"))
        if distance_to_high is not None:
            reasons.append(f"距平台上沿 {distance_to_high * 100:.2f}%")
        recent_gain = safe_float(row.get("platform_setup_recent_gain_5d"))
        if recent_gain is not None:
            reasons.append(f"近5日涨幅 {recent_gain * 100:.2f}%")
        volume_contraction = safe_float(row.get("platform_setup_volume_contraction"))
        if volume_contraction is not None:
            reasons.append(f"缩量比 {volume_contraction:.2f}x")
        bull_volume = safe_float(row.get("platform_setup_bull_volume_ratio"))
        if bull_volume is not None:
            reasons.append(f"阳线量能 {bull_volume:.2f}x")
        ma_convergence = safe_float(row.get("platform_setup_ma_convergence"))
        if ma_convergence is not None:
            reasons.append(f"均线粘合 {ma_convergence * 100:.2f}%")
        if row.get("platform_setup_ma_turning_up"):
            reasons.append("MA5 拐头")
    if strategy.get("signal_mode") == "platform_breakout":
        platform_range = safe_float(row.get("platform_range"))
        if platform_range is not None:
            reasons.append(f"平台振幅 {platform_range * 100:.2f}%")
        breakout_volume = safe_float(row.get("platform_breakout_volume_ratio"))
        if breakout_volume is not None:
            reasons.append(f"突破量比 {breakout_volume:.2f}x")
        body_strength = safe_float(row.get("platform_body_strength"))
        if body_strength is not None:
            reasons.append(f"实体强度 {body_strength:.2f}")
        if row.get("platform_ma_bullish"):
            reasons.append("MA5/10/20 多头")
        macd_dif = safe_float(row.get("macd_dif"))
        if macd_dif is not None and macd_dif > 0:
            reasons.append("MACD 位于 0 轴上方")
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
            latest_price = _first_number((snapshot or {}).get("latest_price"), latest_bar.get("close"))
            ma_short_window = int(strategy.get("ma_short_window") or 20)
            ma_long_window = int(strategy.get("ma_long_window") or 60)
            closes = pd.to_numeric(group["close"], errors="coerce").dropna()
            volumes = pd.to_numeric(group["volume"], errors="coerce").dropna()
            ma_short = float(closes.tail(ma_short_window).mean()) if len(closes) >= ma_short_window else None
            ma_long = float(closes.tail(ma_long_window).mean()) if len(closes) >= ma_long_window else None
            prev_volume_mean = float(volumes.iloc[:-1].tail(20).mean()) if len(volumes) > 1 else None
            latest_volume = _first_number((snapshot or {}).get("volume"), latest_bar.get("volume"))
            volume_ratio = (
                latest_volume / prev_volume_mean
                if latest_volume is not None and prev_volume_mean is not None and prev_volume_mean > 0
                else None
            )
            ma_distance = (
                abs(latest_price - ma_short) / ma_short
                if latest_price is not None and ma_short is not None and ma_short > 0
                else None
            )
            float_mv = (
                _first_number(
                    (float_record or {}).get("float_market_value"),
                    (snapshot or {}).get("float_market_value"),
                )
            )
            platform_metrics = compute_platform_breakout_metrics(group, strategy)
            if strategy.get("signal_mode") == "platform_setup":
                platform_metrics.update(compute_platform_setup_metrics(group, strategy))
            output.append(
                {
                    "code": code,
                    "name": (snapshot or {}).get("name") or latest_bar.get("name") or code,
                    "latest_price": latest_price,
                    "pct_chg": _first_number((snapshot or {}).get("pct_chg"), latest_bar.get("pct_chg")),
                    "amount": _first_number((snapshot or {}).get("amount"), latest_bar.get("amount")),
                    "volume": latest_volume,
                    "turnover_rate": _first_number((snapshot or {}).get("turnover_rate"), latest_bar.get("turn")),
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
                    **platform_metrics,
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


def _first_number(*values: Any) -> Optional[float]:
    for value in values:
        parsed = safe_float(value)
        if parsed is not None:
            return parsed
    return None


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
