from __future__ import annotations

import json
import math
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from backend.app.db import Database
from backend.app.services.indicator_registry import INDICATOR_BY_ID
from backend.app.services.market_utils import safe_float, to_sina_chart_symbol
from backend.app.services.strategy_service import normalize_strategy_config


AnalysisProgress = Callable[[str, int, int], None]
ANALYSIS_TOTAL_STEPS = 7


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

    range_basis = strategy.get("platform_range_basis") or "high_low"
    upper_column = "close" if range_basis == "close" else "high"
    lower_column = "close" if range_basis == "close" else "low"
    platform_high = safe_float(platform[upper_column].max())
    platform_low = safe_float(platform[lower_column].min())
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
    min_clearance = float(strategy.get("platform_breakout_clearance") or 0)
    breakout_clearance = (
        (close_value - platform_high) / platform_high
        if close_value is not None and platform_high is not None and platform_high > 0
        else None
    )
    breakout_above_upper = (
        breakout_clearance is not None
        and breakout_clearance >= min_clearance
    )
    days_above_platform = None
    first_breakout_days = None
    if platform_high is not None and platform_high > 0:
        consecutive = 0
        for value in reversed(clean["close"].tail(platform_days + 1).tolist()):
            close = safe_float(value)
            if close is not None and close > platform_high:
                consecutive += 1
            else:
                break
        if consecutive > 0:
            days_above_platform = consecutive
            first_breakout_days = max(0, consecutive - 1)
    recent_gain_5d = None
    if len(clean) >= 6 and close_value is not None:
        start_close = safe_float(clean.iloc[-6].get("close"))
        if start_close is not None and start_close > 0:
            recent_gain_5d = (close_value - start_close) / start_close
    previous_platform_upper = None
    previous_breakout_clearance = None
    platform_first_breakout = False
    if len(clean) >= platform_days + 2:
        previous_platform = clean.iloc[-platform_days - 2 : -2].dropna(
            subset=["open", "high", "low", "close", "volume"]
        )
        previous_close = safe_float(clean.iloc[-2].get("close"))
        previous_platform_upper = (
            safe_float(previous_platform[upper_column].max())
            if len(previous_platform) >= platform_days
            else None
        )
        previous_breakout_clearance = (
            (previous_close - previous_platform_upper) / previous_platform_upper
            if previous_close is not None and previous_platform_upper is not None and previous_platform_upper > 0
            else None
        )
        platform_first_breakout = bool(
            breakout_above_upper
            and previous_breakout_clearance is not None
            and previous_breakout_clearance < min_clearance
        )
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
        "platform_range_basis": range_basis,
        "platform_upper": _round_optional(platform_high, 6),
        "platform_lower": _round_optional(platform_low, 6),
        "platform_bullish_ratio": _round_optional(bullish_ratio, 6),
        "platform_bull_volume_ratio": _round_optional(bull_volume_ratio, 6),
        "platform_breakout_volume_ratio": _round_optional(breakout_volume_ratio, 6),
        "platform_breakout_bullish": breakout_bullish,
        "platform_breakout_pct_chg": pct_chg,
        "platform_breakout_close": _round_optional(close_value, 6),
        "platform_breakout_clearance": _round_optional(breakout_clearance, 6),
        "platform_breakout_above_upper": bool(breakout_above_upper),
        "platform_days_above_upper": days_above_platform,
        "platform_first_breakout_days": first_breakout_days,
        "platform_recent_gain_5d": _round_optional(recent_gain_5d, 6),
        "platform_previous_upper": _round_optional(previous_platform_upper, 6),
        "platform_previous_breakout_clearance": _round_optional(previous_breakout_clearance, 6),
        "platform_first_breakout": platform_first_breakout,
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


def compute_trend_resonance_metrics(group: pd.DataFrame, strategy: Dict[str, Any]) -> Dict[str, Any]:
    clean = group.copy().sort_values("date")
    for column in ["open", "high", "low", "close", "volume"]:
        clean[column] = pd.to_numeric(clean.get(column), errors="coerce")

    ema_fast_window = max(2, int(strategy.get("trend_ema_fast_window") or 13))
    ema_mid_window = max(ema_fast_window + 1, int(strategy.get("trend_ema_mid_window") or 21))
    ema_long_window = max(ema_mid_window + 1, int(strategy.get("trend_ema_long_window") or 60))
    stoch_window = max(5, int(strategy.get("trend_stoch_window") or 27))
    k_smooth = max(1, int(strategy.get("trend_stoch_k_smooth") or 9))
    d_smooth = max(1, int(strategy.get("trend_stoch_d_smooth") or 3))
    required_rows = max(ema_long_window + 2, int(strategy.get("trend_macd_slow") or 26) + int(strategy.get("trend_macd_signal") or 6) + 2, stoch_window + k_smooth + d_smooth)
    clean = clean.dropna(subset=["high", "low", "close"])
    if len(clean) < required_rows:
        return {"trend_ready": False}

    close = clean["close"]
    latest_close = safe_float(close.iloc[-1])
    prev_close = safe_float(close.iloc[-2])
    ema_fast_series = close.ewm(span=ema_fast_window, adjust=False).mean()
    ema_mid_series = close.ewm(span=ema_mid_window, adjust=False).mean()
    ema_long_series = close.ewm(span=ema_long_window, adjust=False).mean()
    ema_fast = safe_float(ema_fast_series.iloc[-1])
    ema_mid = safe_float(ema_mid_series.iloc[-1])
    ema_long = safe_float(ema_long_series.iloc[-1])
    prev_ema_fast = safe_float(ema_fast_series.iloc[-2])
    prev_ema_mid = safe_float(ema_mid_series.iloc[-2])
    prev_ema_long = safe_float(ema_long_series.iloc[-2])

    macd_dif, macd_dea, macd_hist = _macd_values(
        close,
        int(strategy.get("trend_macd_fast") or 4),
        int(strategy.get("trend_macd_slow") or 26),
        int(strategy.get("trend_macd_signal") or 6),
        include_hist=True,
    )
    stoch_k, stoch_d, prev_stoch_k, prev_stoch_d = _slow_stochastic_values(
        clean["high"],
        clean["low"],
        close,
        stoch_window,
        k_smooth,
        d_smooth,
    )
    recent_gain_10d = None
    if len(close) >= 11:
        base = safe_float(close.iloc[-11])
        if base is not None and latest_close is not None and base > 0:
            recent_gain_10d = (latest_close - base) / base
    ema_mid_distance = (
        (latest_close - ema_mid) / ema_mid
        if latest_close is not None and ema_mid is not None and ema_mid > 0
        else None
    )

    price_above_ema_long = latest_close is not None and ema_long is not None and latest_close > ema_long
    ema_fast_above_mid = ema_fast is not None and ema_mid is not None and ema_fast > ema_mid
    ema_long_rising = ema_long is not None and prev_ema_long is not None and ema_long > prev_ema_long
    ema_fast_rising = ema_fast is not None and prev_ema_fast is not None and ema_fast > prev_ema_fast
    ema_mid_rising = ema_mid is not None and prev_ema_mid is not None and ema_mid > prev_ema_mid
    macd_dif_above_dea = macd_dif is not None and macd_dea is not None and macd_dif > macd_dea
    macd_dif_above_zero = macd_dif is not None and macd_dif > 0
    stoch_k_above_d = stoch_k is not None and stoch_d is not None and stoch_k > stoch_d
    stoch_cross_up = (
        stoch_k_above_d
        and prev_stoch_k is not None
        and prev_stoch_d is not None
        and prev_stoch_k <= prev_stoch_d
    )
    overheat_level = safe_float(strategy.get("trend_stoch_overheat")) or 85.0
    stoch_overheated = stoch_k is not None and stoch_k >= overheat_level

    thunder = bool(price_above_ema_long and ema_fast_above_mid and macd_dif_above_dea and stoch_k_above_d)
    follow = bool(price_above_ema_long and ema_fast_above_mid and macd_dif_above_zero)
    stealth = bool(price_above_ema_long and ema_fast_rising and ema_mid_rising and macd_dif_above_dea and not stoch_overheated)
    entry_signal = strategy.get("trend_entry_signal") or "any"
    if entry_signal == "thunder":
        signal_match = thunder
    elif entry_signal == "follow":
        signal_match = follow
    elif entry_signal == "stealth":
        signal_match = stealth
    else:
        signal_match = thunder or follow or stealth
    signal_label = "强动能确认" if thunder else "趋势延续" if follow else "早期转强" if stealth else "趋势观察"

    return {
        "trend_ready": True,
        "trend_close": _round_optional(latest_close, 6),
        "trend_prev_close": _round_optional(prev_close, 6),
        "trend_ema_fast": _round_optional(ema_fast, 6),
        "trend_ema_mid": _round_optional(ema_mid, 6),
        "trend_ema_long": _round_optional(ema_long, 6),
        "trend_price_above_ema_long": bool(price_above_ema_long),
        "trend_ema_fast_above_mid": bool(ema_fast_above_mid),
        "trend_ema_long_rising": bool(ema_long_rising),
        "trend_ema_fast_rising": bool(ema_fast_rising),
        "trend_ema_mid_rising": bool(ema_mid_rising),
        "trend_ema_mid_distance": _round_optional(ema_mid_distance, 6),
        "trend_recent_gain_10d": _round_optional(recent_gain_10d, 6),
        "trend_macd_dif": _round_optional(macd_dif, 6),
        "trend_macd_dea": _round_optional(macd_dea, 6),
        "trend_macd_hist": _round_optional(macd_hist, 6),
        "trend_macd_dif_above_dea": bool(macd_dif_above_dea),
        "trend_macd_dif_above_zero": bool(macd_dif_above_zero),
        "trend_stoch_k": _round_optional(stoch_k, 6),
        "trend_stoch_d": _round_optional(stoch_d, 6),
        "trend_stoch_k_above_d": bool(stoch_k_above_d),
        "trend_stoch_cross_up": bool(stoch_cross_up),
        "trend_stoch_overheated": bool(stoch_overheated),
        "trend_thunder_signal": thunder,
        "trend_follow_signal": follow,
        "trend_stealth_signal": stealth,
        "trend_signal_match": bool(signal_match),
        "trend_signal_label": signal_label,
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


def _macd_values(
    closes: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    include_hist: bool = False,
) -> Tuple[Optional[float], Optional[float]] | Tuple[Optional[float], Optional[float], Optional[float]]:
    clean = pd.to_numeric(closes, errors="coerce").dropna()
    if len(clean) < slow + signal:
        return (None, None, None) if include_hist else (None, None)
    ema_fast = clean.ewm(span=fast, adjust=False).mean()
    ema_slow = clean.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = (dif - dea) * 2
    if include_hist:
        return float(dif.iloc[-1]), float(dea.iloc[-1]), float(hist.iloc[-1])
    return float(dif.iloc[-1]), float(dea.iloc[-1])


def _slow_stochastic_values(
    highs: pd.Series,
    lows: pd.Series,
    closes: pd.Series,
    window: int,
    k_smooth: int,
    d_smooth: int,
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    high = pd.to_numeric(highs, errors="coerce")
    low = pd.to_numeric(lows, errors="coerce")
    close = pd.to_numeric(closes, errors="coerce")
    lowest = low.rolling(window=window, min_periods=window).min()
    highest = high.rolling(window=window, min_periods=window).max()
    spread = highest - lowest
    safe_spread = spread.mask(spread == 0, float("nan"))
    raw_k = pd.to_numeric(((close - lowest) / safe_spread) * 100, errors="coerce")
    slow_k = raw_k.rolling(window=k_smooth, min_periods=k_smooth).mean()
    slow_d = slow_k.rolling(window=d_smooth, min_periods=d_smooth).mean()
    valid = pd.DataFrame({"k": slow_k, "d": slow_d}).dropna()
    if len(valid) < 2:
        return None, None, None, None
    latest = valid.iloc[-1]
    previous = valid.iloc[-2]
    return float(latest["k"]), float(latest["d"]), float(previous["k"]), float(previous["d"])


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

    working = _apply_theme_filters(working, strategy, funnel)
    working = _apply_strategy_rule_filters(working, strategy, funnel)

    feature_engines = _feature_engines(strategy)

    if strategy.get("analysis_mode") == "score":
        if "platform_breakout" in feature_engines:
            working = _apply_platform_breakout_filters(working, strategy, funnel)
            if working.empty:
                zero_reason = _zero_reason(funnel)
                return [], funnel, zero_reason
        if "platform_setup" in feature_engines:
            working = _apply_platform_setup_filters(working, strategy, funnel)
            if working.empty:
                zero_reason = _zero_reason(funnel)
                return [], funnel, zero_reason
        if "trend_resonance" in feature_engines:
            working = _apply_trend_resonance_filters(working, strategy, funnel)
            if working.empty:
                zero_reason = _zero_reason(funnel)
                return [], funnel, zero_reason
        return _rank_candidates(
            working,
            strategy,
            funnel,
            score_mode=True,
        )

    if strategy.get("trend_filter") == "ma_short_above_long" and "trend_resonance" not in feature_engines:
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
    if "platform_setup" not in feature_engines:
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
    if "platform_breakout" in feature_engines:
        working = _apply_platform_breakout_filters(working, strategy, funnel)
    if "platform_setup" in feature_engines:
        working = _apply_platform_setup_filters(working, strategy, funnel)
    if "trend_resonance" in feature_engines:
        working = _apply_trend_resonance_filters(working, strategy, funnel)

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
        candidate["score_breakdown"] = _score_breakdown(candidate, strategy)
        candidate["strategy_rule_results"] = _strategy_rule_results(candidate, strategy)
        candidate["display_metrics"] = _display_metrics(candidate, strategy)
        candidate["freshness"] = _freshness_metrics(candidate, strategy)
        candidate["interpretation"] = _candidate_interpretation(candidate, strategy)
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


def _strategy_rule_indicator(rule: Dict[str, Any], action: str) -> Optional[Dict[str, Any]]:
    indicator = INDICATOR_BY_ID.get(str(rule.get("indicator_id") or ""))
    if not indicator:
        return None
    if action == "display" and indicator.get("data_status") in {"executable", "display_only"}:
        return indicator if "display" in (indicator.get("supported_actions") or []) else None
    if indicator.get("data_status") != "executable":
        return None
    if action == "interaction" and "interaction" in (indicator.get("usage") or []):
        return indicator
    if action not in (indicator.get("supported_actions") or []):
        return None
    return indicator


def _apply_strategy_rule_filters(
    frame: pd.DataFrame,
    strategy: Dict[str, Any],
    funnel: List[Dict[str, Any]],
) -> pd.DataFrame:
    working = frame
    for rule in strategy.get("strategy_rules") or []:
        if not rule.get("enabled", True) or rule.get("action") != "filter":
            continue
        indicator = _strategy_rule_indicator(rule, "filter")
        if not indicator:
            raw_indicator = INDICATOR_BY_ID.get(str(rule.get("indicator_id") or ""))
            if raw_indicator:
                funnel.append(
                    {
                        "step_name": f"{raw_indicator.get('name') or raw_indicator.get('id')}规则",
                        "before_count": int(len(working)),
                        "after_count": int(len(working)),
                        "removed_count": 0,
                        "note": "指标不支持筛选，规则已忽略",
                    }
                )
            continue
        column = str(indicator.get("analysis_field") or indicator.get("id") or "")
        if column not in working.columns:
            funnel.append(
                {
                    "step_name": f"{indicator.get('name') or column}规则",
                    "before_count": int(len(working)),
                    "after_count": int(len(working)),
                    "removed_count": 0,
                    "note": "字段尚未进入分析帧，规则已忽略",
                }
            )
            continue
        before = len(working)
        mask = _strategy_rule_mask(working[column], rule)
        working = working[mask]
        funnel.append(
            {
                "step_name": f"{indicator.get('name') or column}规则",
                "before_count": int(before),
                "after_count": int(len(working)),
                "removed_count": int(before - len(working)),
                "note": _strategy_rule_note(indicator, rule),
            }
        )
    return working


def _strategy_rule_mask(series: pd.Series, rule: Dict[str, Any], missing_matches: bool = True) -> pd.Series:
    operator = str(rule.get("operator") or "gte")
    value = rule.get("value")
    value2 = rule.get("value2")
    missing_policy = str(rule.get("missing_policy") or "neutral")
    missing_mask = series.isna()
    if operator == "is_true":
        mask = series.fillna(False).astype(bool)
    elif operator in {"eq", "neq"} and isinstance(value, bool):
        mask = series.fillna(False).astype(bool) == value
        if operator == "neq":
            mask = ~mask
    else:
        numeric = pd.to_numeric(series, errors="coerce")
        target = safe_float(value)
        target2 = safe_float(value2)
        if target is None and operator not in {"eq", "neq"}:
            mask = pd.Series(True, index=series.index)
        elif operator == "gte":
            mask = numeric >= float(target)
        elif operator == "lte":
            mask = numeric <= float(target)
        elif operator == "gt":
            mask = numeric > float(target)
        elif operator == "lt":
            mask = numeric < float(target)
        elif operator == "between":
            if target is None or target2 is None:
                mask = pd.Series(True, index=series.index)
            else:
                low = min(float(target), float(target2))
                high = max(float(target), float(target2))
                mask = (numeric >= low) & (numeric <= high)
        elif operator == "eq":
            if target is None:
                mask = series.astype(str) == str(value)
            else:
                mask = numeric == float(target)
        elif operator == "neq":
            if target is None:
                mask = series.astype(str) != str(value)
            else:
                mask = numeric != float(target)
        elif operator == "recent":
            window = int(rule.get("window_days") or safe_float(value) or 0)
            mask = numeric <= window if window > 0 else pd.Series(True, index=series.index)
        else:
            mask = pd.Series(True, index=series.index)
    if missing_matches and missing_policy in {"keep", "allow", "neutral"}:
        mask = mask | missing_mask
    return mask.fillna(False)


def _value_missing(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return value is None


def _missing_keeps_rule(rule: Dict[str, Any]) -> bool:
    return str(rule.get("missing_policy") or "neutral") in {"keep", "allow", "neutral"}


def _strategy_rule_note(indicator: Dict[str, Any], rule: Dict[str, Any]) -> str:
    operator_labels = {
        "gte": ">=",
        "lte": "<=",
        "gt": ">",
        "lt": "<",
        "between": "介于",
        "eq": "=",
        "neq": "!=",
        "is_true": "为真",
        "recent": "最近",
    }
    operator = operator_labels.get(str(rule.get("operator") or ""), str(rule.get("operator") or ""))
    unit = str(indicator.get("unit") or "")
    value = rule.get("value")
    value2 = rule.get("value2")
    if rule.get("operator") == "between":
        return f"{operator} {value} - {value2}{unit}"
    if rule.get("operator") == "is_true":
        return operator
    return f"{operator} {value}{unit}".strip()


def _strategy_rule_matches_row(row: Dict[str, Any], rule: Dict[str, Any], action: str) -> bool:
    indicator = _strategy_rule_indicator(rule, action)
    if not indicator:
        return False
    column = str(indicator.get("analysis_field") or indicator.get("id") or "")
    if column not in row:
        return action == "filter" and _missing_keeps_rule(rule)
    value = row.get(column)
    if _value_missing(value):
        return action == "filter" and _missing_keeps_rule(rule)
    series = pd.Series([value])
    return bool(_strategy_rule_mask(series, rule, missing_matches=False).iloc[0])


def _strategy_rule_value(row: Dict[str, Any], indicator: Dict[str, Any]) -> Any:
    column = str(indicator.get("analysis_field") or indicator.get("id") or "")
    return row.get(column)


def _strategy_rule_results(row: Dict[str, Any], strategy: Dict[str, Any]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for rule in strategy.get("strategy_rules") or []:
        if not rule.get("enabled", True):
            continue
        action = str(rule.get("action") or "display")
        indicator = _strategy_rule_indicator(rule, action)
        if not indicator:
            continue
        column = str(indicator.get("analysis_field") or indicator.get("id") or "")
        value = _strategy_rule_value(row, indicator) if column in row else None
        missing = column not in row or _value_missing(value)
        matched = True if action == "display" else _strategy_rule_matches_row(row, rule, action)
        weight = safe_float(rule.get("weight"))
        if weight is None:
            weight = 5.0
        adjustment = 0.0
        reason = None
        if matched and action == "score":
            adjustment = float(weight)
        elif matched and action == "risk":
            adjustment = -float(weight)
        elif missing and action == "score":
            reason = "字段缺失，未加分"
        elif missing and action == "risk":
            reason = "字段缺失，未扣风险"
        elif missing and action == "filter":
            reason = "字段缺失，按缺失策略保留" if matched else "字段缺失，未命中"
        results.append(
            {
                "rule_id": str(rule.get("id") or ""),
                "indicator_id": str(rule.get("indicator_id") or ""),
                "indicator_name": str(indicator.get("name") or indicator.get("id") or ""),
                "action": action,
                "matched": bool(matched),
                "missing": bool(missing),
                "value": value,
                "adjustment": round(adjustment, 2),
                "reason": reason,
            }
        )
    return results


def _display_metrics(row: Dict[str, Any], strategy: Dict[str, Any]) -> Dict[str, Any]:
    display: Dict[str, Any] = {}
    for rule in strategy.get("strategy_rules") or []:
        if not rule.get("enabled", True) or rule.get("action") != "display":
            continue
        indicator = _strategy_rule_indicator(rule, "display")
        if not indicator:
            continue
        column = str(indicator.get("analysis_field") or indicator.get("id") or "")
        if column in row:
            display[column] = row.get(column)
    return display


def _strategy_condition_matches_row(row: Dict[str, Any], condition: Dict[str, Any]) -> bool:
    indicator = INDICATOR_BY_ID.get(str(condition.get("indicator_id") or ""))
    if not indicator or indicator.get("data_status") != "executable":
        return False
    column = str(indicator.get("analysis_field") or indicator.get("id") or "")
    if column not in row:
        return False
    value = row.get(column)
    try:
        value_missing = bool(pd.isna(value))
    except (TypeError, ValueError):
        value_missing = value is None
    if value_missing:
        return str(condition.get("missing_policy") or "neutral") in {"keep", "allow"}
    series = pd.Series([value])
    return bool(_strategy_rule_mask(series, condition).iloc[0])


def _strategy_rule_score_adjustment(row: Dict[str, Any], strategy: Dict[str, Any]) -> float:
    adjustment = 0.0
    for rule in strategy.get("strategy_rules") or []:
        if not rule.get("enabled", True) or rule.get("action") not in {"score", "risk"}:
            continue
        action = str(rule.get("action"))
        if not _strategy_rule_matches_row(row, rule, action):
            continue
        weight = safe_float(rule.get("weight"))
        if weight is None:
            weight = 5.0
        adjustment += float(weight) if action == "score" else -float(weight)
    return round(adjustment, 2)


def _strategy_rules_by_id(strategy: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        str(rule.get("id") or ""): rule
        for rule in strategy.get("strategy_rules") or []
        if isinstance(rule, dict) and rule.get("id")
    }


def _matching_strategy_resonances(row: Dict[str, Any], strategy: Dict[str, Any]) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    rules_by_id = _strategy_rules_by_id(strategy)
    for resonance in strategy.get("strategy_resonances") or []:
        if not resonance.get("enabled", True):
            continue
        rule_ids = [str(rule_id) for rule_id in resonance.get("rule_ids") or []]
        rules = [rules_by_id.get(rule_id) for rule_id in rule_ids]
        if len([rule for rule in rules if rule is not None]) != len(rule_ids) or len(rules) < 2:
            continue
        if any(str(rule.get("action") or "") not in {"filter", "score"} for rule in rules if rule is not None):
            continue
        if all(_strategy_rule_matches_row(row, rule, str(rule.get("action") or "display")) for rule in rules if rule is not None):
            matches.append(resonance)
    return matches


def _strategy_resonance_bonus(row: Dict[str, Any], strategy: Dict[str, Any]) -> float:
    bonus = 0.0
    for resonance in _matching_strategy_resonances(row, strategy):
        value = safe_float(resonance.get("bonus"))
        if value is not None:
            bonus += float(value)
    cap = safe_float(strategy.get("resonance_bonus_cap"))
    if cap is None:
        cap = 15.0
    return round(min(max(bonus, 0.0), max(float(cap), 0.0)), 2)


def _apply_theme_filters(
    frame: pd.DataFrame,
    strategy: Dict[str, Any],
    funnel: List[Dict[str, Any]],
) -> pd.DataFrame:
    working = _numeric_filter(
        frame,
        "topic_count",
        strategy.get("min_topic_count"),
        None,
        "题材数量",
        funnel,
    )
    working = _numeric_filter(
        working,
        "topic_heat",
        strategy.get("min_topic_heat"),
        None,
        "题材热度",
        funnel,
    )
    return _numeric_filter(
        working,
        "theme_limit_count",
        strategy.get("min_theme_limit_count"),
        None,
        "题材涨停数",
        funnel,
    )


def _apply_platform_breakout_filters(
    frame: pd.DataFrame,
    strategy: Dict[str, Any],
    funnel: List[Dict[str, Any]],
) -> pd.DataFrame:
    working = _bool_filter(frame, "platform_ready", "平台数据", funnel, "需要足够历史 K 线")
    if _condition_mode(strategy, "platform_max_range_mode", "must") == "must":
        working = _numeric_filter(
            working,
            "platform_range",
            None,
            strategy.get("platform_max_range"),
            "平台振幅",
            funnel,
        )
    clearance_mode = _condition_mode(
        strategy,
        "platform_breakout_clearance_mode",
        "must" if strategy.get("platform_breakout_require_close_above") else "off",
    )
    if clearance_mode == "must":
        working = _numeric_filter(
            working,
            "platform_breakout_clearance",
            strategy.get("platform_breakout_clearance"),
            None,
            "突破上沿",
            funnel,
        )
    if _condition_mode(strategy, "platform_breakout_max_clearance_mode", "must") == "must":
        working = _numeric_filter(
            working,
            "platform_breakout_clearance",
            None,
            strategy.get("platform_breakout_max_clearance"),
            "突破距离",
            funnel,
        )
    if _condition_mode(strategy, "platform_breakout_first_mode", "score") == "must":
        working = _bool_filter(working, "platform_first_breakout", "首次突破", funnel, "前一交易日未有效站上平台上沿")
    if _condition_mode(strategy, "platform_bullish_ratio_mode", "must") == "must":
        working = _numeric_filter(
            working,
            "platform_bullish_ratio",
            strategy.get("platform_min_bullish_ratio"),
            None,
            "阳线占比",
            funnel,
        )
    if _condition_mode(strategy, "platform_bull_volume_advantage_mode", "must") == "must":
        working = _numeric_filter(
            working,
            "platform_bull_volume_ratio",
            strategy.get("platform_bull_volume_advantage"),
            None,
            "阳线量能",
            funnel,
        )
    if _condition_mode(strategy, "platform_breakout_volume_ratio_mode", "must") == "must":
        working = _numeric_filter(
            working,
            "platform_breakout_volume_ratio",
            strategy.get("platform_breakout_volume_ratio"),
            None,
            "突破量比",
            funnel,
        )
    if _condition_mode(strategy, "platform_breakout_pct_chg_mode", "must") == "must":
        working = _numeric_filter(
            working,
            "platform_breakout_pct_chg",
            strategy.get("platform_breakout_pct_chg_min"),
            None,
            "突破涨幅",
            funnel,
        )
    if _condition_mode(strategy, "platform_breakout_bullish_mode", "must") == "must":
        working = _bool_filter(working, "platform_breakout_bullish", "突破阳线", funnel, "突破当日为红柱")
    if _condition_mode(strategy, "platform_body_strength_mode", "must") == "must":
        working = _numeric_filter(
            working,
            "platform_body_strength",
            strategy.get("platform_body_strength_min"),
            None,
            "实体强度",
            funnel,
        )
    if _condition_mode(strategy, "platform_ma_bullish_mode", "score") == "must":
        working = _bool_filter(working, "platform_ma_bullish", "MA5/10/20 多头", funnel, "MA5 > MA10 > MA20")
    if _condition_mode(strategy, "platform_ma_rising_mode", "score") == "must":
        working = _bool_filter(working, "platform_ma_rising", "均线上升", funnel, "MA5/10/20 均向上")
    if _condition_mode(strategy, "platform_macd_filter_mode", "score") == "must":
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


def _apply_trend_resonance_filters(
    frame: pd.DataFrame,
    strategy: Dict[str, Any],
    funnel: List[Dict[str, Any]],
) -> pd.DataFrame:
    working = _bool_filter(frame, "trend_ready", "趋势数据", funnel, "需要足够历史 K 线")
    if strategy.get("trend_require_price_above_ema_long"):
        working = _bool_filter(working, "trend_price_above_ema_long", "价格站上 EMA60", funnel, "最新收盘在中期趋势线上方")
    if strategy.get("trend_require_ema_long_rising"):
        working = _bool_filter(working, "trend_ema_long_rising", "EMA60 上升", funnel, "中期趋势线向上")
    if strategy.get("trend_require_ema_fast_above_mid"):
        working = _bool_filter(working, "trend_ema_fast_above_mid", "EMA13/21 多头", funnel, "EMA13 在 EMA21 上方")
    working = _numeric_filter(
        working,
        "trend_ema_mid_distance",
        None,
        strategy.get("trend_max_ema_mid_distance"),
        "EMA21 乖离",
        funnel,
    )
    working = _numeric_filter(
        working,
        "trend_recent_gain_10d",
        None,
        strategy.get("trend_max_recent_gain_10d"),
        "短线不过热",
        funnel,
    )
    macd_mode = strategy.get("trend_macd_mode") or "dif_above_dea"
    if macd_mode != "off":
        before = len(working)
        dif = pd.to_numeric(working.get("trend_macd_dif"), errors="coerce")
        dea = pd.to_numeric(working.get("trend_macd_dea"), errors="coerce")
        if macd_mode == "dif_dea_above_zero":
            mask = (dif > dea) & (dif > 0) & (dea > 0)
            note = "DIF 强于 DEA，且二者在 0 轴上方"
        elif macd_mode == "dif_above_zero":
            mask = dif > 0
            note = "DIF 在 0 轴上方"
        else:
            mask = dif > dea
            note = "DIF 强于 DEA"
        working = working[mask]
        funnel.append(
            {
                "step_name": "MACD 共振",
                "before_count": int(before),
                "after_count": int(len(working)),
                "removed_count": int(before - len(working)),
                "note": note,
            }
        )
    stoch_mode = strategy.get("trend_stoch_mode") or "k_above_d"
    if stoch_mode != "off":
        column = "trend_stoch_cross_up" if stoch_mode == "cross_up" else "trend_stoch_k_above_d"
        step = "随机指标金叉" if stoch_mode == "cross_up" else "随机指标共振"
        note = "慢速随机指标 K 上穿 D" if stoch_mode == "cross_up" else "慢速随机指标 K 在 D 上方"
        working = _bool_filter(working, column, step, funnel, note)
    working = _bool_filter(working, "trend_signal_match", "趋势信号", funnel, "强动能确认、趋势延续或早期转强至少一种成立")
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


def _condition_mode(strategy: Dict[str, Any], key: str, default: str) -> str:
    value = strategy.get(key)
    if value in {"must", "score", "off"}:
        return str(value)
    return default


def _feature_engines(strategy: Dict[str, Any]) -> set[str]:
    return {
        str(engine)
        for engine in (strategy.get("analysis_engines") or [])
        if str(engine) in {"platform_breakout", "platform_setup", "trend_resonance"}
    }


def _theme_score_bonus(row: Dict[str, Any], strategy: Dict[str, Any]) -> float:
    bonus = 0.0
    topic_count = safe_float(row.get("topic_count"))
    topic_heat = safe_float(row.get("topic_heat"))
    theme_limit_count = safe_float(row.get("theme_limit_count"))
    min_topic_count = safe_float(strategy.get("min_topic_count"))
    min_topic_heat = safe_float(strategy.get("min_topic_heat"))
    min_theme_limit_count = safe_float(strategy.get("min_theme_limit_count"))
    if min_topic_count is not None and topic_count is not None:
        bonus += 4 if topic_count >= min_topic_count else -4
    if min_topic_heat is not None and topic_heat is not None:
        bonus += min(topic_heat / max(min_topic_heat, 1.0), 1.4) * 8 if topic_heat >= min_topic_heat else -8
    if min_theme_limit_count is not None and theme_limit_count is not None:
        bonus += 6 if theme_limit_count >= min_theme_limit_count else -6
    return bonus


def _signal_type(row: Dict[str, Any], strategy: Dict[str, Any]) -> str:
    feature_engines = _feature_engines(strategy)
    if "platform_setup" in feature_engines:
        return "平台临界"
    if "platform_breakout" in feature_engines:
        if strategy.get("analysis_mode") == "score":
            return "平台突破观察"
        return "平台突破"
    if "trend_resonance" in feature_engines:
        return str(row.get("trend_signal_label") or "趋势共振")
    distance = safe_float(row.get("ma_distance"))
    volume_ratio = safe_float(row.get("volume_ratio")) or 0
    direction = strategy.get("breakout_pullback_direction") or "both"
    if direction == "pullback":
        return "左侧回踩"
    if direction == "breakout":
        return "右侧突破"
    if distance is not None and distance <= float(strategy.get("pullback_tolerance") or 0.04):
        return "左侧回踩"
    if volume_ratio >= float(strategy.get("volume_ratio_min") or 1.0):
        return "右侧突破"
    return "趋势观察"


def _with_strategy_rule_adjustment(score: float, row: Dict[str, Any], strategy: Dict[str, Any]) -> float:
    adjusted = max(score + _strategy_rule_score_adjustment(row, strategy) + _strategy_resonance_bonus(row, strategy), 0)
    return round(adjusted, 2)


def _signal_score(row: Dict[str, Any], strategy: Dict[str, Any]) -> float:
    feature_engines = _feature_engines(strategy)
    rps = safe_float(row.get(f"rps{int(strategy.get('rps_window') or 20)}")) or safe_float(row.get("rps20")) or 0
    theme_bonus = _theme_score_bonus(row, strategy)
    if "platform_setup" in feature_engines:
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
        return _with_strategy_rule_adjustment(score + theme_bonus, row, strategy)
    if "platform_breakout" in feature_engines:
        platform_range = safe_float(row.get("platform_range"))
        bullish_ratio = safe_float(row.get("platform_bullish_ratio"))
        bull_volume_ratio = safe_float(row.get("platform_bull_volume_ratio"))
        breakout_volume_ratio = safe_float(row.get("platform_breakout_volume_ratio"))
        breakout_pct = safe_float(row.get("platform_breakout_pct_chg"))
        breakout_clearance = safe_float(row.get("platform_breakout_clearance"))
        body_strength = safe_float(row.get("platform_body_strength"))
        range_mode = _condition_mode(strategy, "platform_max_range_mode", "must")
        bullish_ratio_mode = _condition_mode(strategy, "platform_bullish_ratio_mode", "must")
        bull_volume_mode = _condition_mode(strategy, "platform_bull_volume_advantage_mode", "must")
        breakout_volume_mode = _condition_mode(strategy, "platform_breakout_volume_ratio_mode", "must")
        breakout_pct_mode = _condition_mode(strategy, "platform_breakout_pct_chg_mode", "must")
        breakout_bullish_mode = _condition_mode(strategy, "platform_breakout_bullish_mode", "must")
        body_strength_mode = _condition_mode(strategy, "platform_body_strength_mode", "must")
        ma_bullish_mode = _condition_mode(strategy, "platform_ma_bullish_mode", "score")
        ma_rising_mode = _condition_mode(strategy, "platform_ma_rising_mode", "score")
        macd_filter_mode = _condition_mode(strategy, "platform_macd_filter_mode", "score")
        dif = safe_float(row.get("macd_dif"))
        dea = safe_float(row.get("macd_dea"))
        if strategy.get("macd_position") == "dif_dea_above_zero":
            macd_ok = dif is not None and dea is not None and dif > 0 and dea > 0
        else:
            macd_ok = dif is not None and dif > 0

        breakout_volume = min((breakout_volume_ratio or 0) * 7, 24) if breakout_volume_mode != "off" else 0
        bull_volume = min((bull_volume_ratio or 0) * 7, 14) if bull_volume_mode != "off" else 0
        pct_bonus = min(max(breakout_pct or 0, 0) * 1.2, 14) if breakout_pct_mode != "off" else 0
        trend_bonus = 10 if ma_bullish_mode != "off" and row.get("platform_ma_bullish") else 0
        macd_bonus = 6 if macd_filter_mode != "off" and macd_ok else 0
        range_penalty = min((platform_range or 0) * 80, 8) if range_mode != "off" else 0
        score = float(rps) * 0.45 + breakout_volume + bull_volume + pct_bonus + trend_bonus + macd_bonus - range_penalty

        max_range = safe_float(strategy.get("platform_max_range"))
        min_bullish_ratio = safe_float(strategy.get("platform_min_bullish_ratio"))
        score_bullish_ratio = safe_float(strategy.get("platform_bullish_ratio_score"))
        min_bull_volume = safe_float(strategy.get("platform_bull_volume_advantage"))
        score_bull_volume = safe_float(strategy.get("platform_bull_volume_advantage_score"))
        min_breakout_volume = safe_float(strategy.get("platform_breakout_volume_ratio"))
        min_breakout_pct = safe_float(strategy.get("platform_breakout_pct_chg_min"))
        min_body_strength = safe_float(strategy.get("platform_body_strength_min"))
        min_clearance = safe_float(strategy.get("platform_breakout_clearance")) or 0
        max_clearance = safe_float(strategy.get("platform_breakout_max_clearance"))
        min_rps = safe_float(strategy.get(f"min_rps{int(strategy.get('rps_window') or 20)}")) or safe_float(
            strategy.get("min_rps20")
        )

        if range_mode != "off" and max_range is not None and platform_range is not None:
            score += 7 if platform_range <= max_range else -min((platform_range - max_range) * 70, 8)
        if _condition_mode(strategy, "platform_breakout_clearance_mode", "must") != "off" and breakout_clearance is not None:
            score += 8 if breakout_clearance >= min_clearance else -8
        if (
            _condition_mode(strategy, "platform_breakout_max_clearance_mode", "must") != "off"
            and breakout_clearance is not None
            and max_clearance is not None
            and max_clearance > 0
        ):
            if breakout_clearance <= max_clearance:
                score += max(0.0, (max_clearance - breakout_clearance) / max_clearance) * 8
            else:
                score -= min((breakout_clearance - max_clearance) * 160, 18)
        if _condition_mode(strategy, "platform_breakout_first_mode", "score") != "off":
            score += 6 if row.get("platform_first_breakout") else -8
        if breakout_volume_mode != "off" and min_breakout_volume is not None and breakout_volume_ratio is not None:
            if breakout_volume_ratio >= min_breakout_volume:
                score += 8
            elif breakout_volume_ratio >= min_breakout_volume * 0.7:
                score += 3
        if (
            bullish_ratio_mode != "off"
            and min_bullish_ratio is not None
            and bullish_ratio is not None
            and bullish_ratio >= min_bullish_ratio
        ):
            score += 2
        if bullish_ratio_mode != "off" and score_bullish_ratio is not None and bullish_ratio is not None:
            score += 5 if bullish_ratio >= score_bullish_ratio else 0
        if (
            bull_volume_mode != "off"
            and min_bull_volume is not None
            and bull_volume_ratio is not None
            and bull_volume_ratio >= min_bull_volume
        ):
            score += 2
        if bull_volume_mode != "off" and score_bull_volume is not None and bull_volume_ratio is not None:
            score += 5 if bull_volume_ratio >= score_bull_volume else 0
        if (
            breakout_pct_mode != "off"
            and body_strength_mode != "off"
            and breakout_bullish_mode != "off"
            and min_breakout_pct is not None
            and min_body_strength is not None
            and breakout_pct is not None
            and body_strength is not None
            and breakout_pct >= min_breakout_pct
            and body_strength >= min_body_strength
            and row.get("platform_breakout_bullish")
        ):
            score += 5
        if min_rps is not None and rps >= min_rps and ma_bullish_mode != "off" and row.get("platform_ma_bullish"):
            score += 6
        if ma_rising_mode != "off":
            score += 5 if row.get("platform_ma_rising") else -3
        if ma_rising_mode != "off" and row.get("platform_ma_rising") and macd_bonus > 0:
            score += 4
        return _with_strategy_rule_adjustment(score + theme_bonus, row, strategy)
    if "trend_resonance" in feature_engines:
        score = float(rps) * 0.38
        if row.get("trend_price_above_ema_long"):
            score += 10
        if row.get("trend_ema_long_rising"):
            score += 12
        if row.get("trend_ema_fast_above_mid"):
            score += 10
        if row.get("trend_ema_fast_rising"):
            score += 5
        if row.get("trend_ema_mid_rising"):
            score += 5
        if row.get("trend_macd_dif_above_dea"):
            score += 10
        if row.get("trend_macd_dif_above_zero"):
            score += 6
        if row.get("trend_stoch_k_above_d"):
            score += 8
        if row.get("trend_stoch_cross_up"):
            score += 4
        if row.get("trend_thunder_signal"):
            score += 8
        elif row.get("trend_follow_signal"):
            score += 5
        elif row.get("trend_stealth_signal"):
            score += 6
        distance = safe_float(row.get("trend_ema_mid_distance"))
        max_distance = safe_float(strategy.get("trend_max_ema_mid_distance")) or 0.12
        if distance is not None:
            if distance <= max_distance:
                score += max(0.0, (max_distance - max(distance, 0.0)) / max_distance) * 8
            else:
                score -= min((distance - max_distance) * 100, 18)
        recent_gain = safe_float(row.get("trend_recent_gain_10d"))
        max_gain = safe_float(strategy.get("trend_max_recent_gain_10d")) or 0.28
        if recent_gain is not None and recent_gain > max_gain:
            score -= min((recent_gain - max_gain) * 80, 18)
        if row.get("trend_stoch_overheated"):
            score -= 8
        score += min((safe_float(row.get("volume_ratio")) or 0) * 4, 10)
        score += min((safe_float(row.get("turnover_rate")) or 0) * 0.8, 8)
        return _with_strategy_rule_adjustment(score + theme_bonus, row, strategy)
    volume_ratio = min((safe_float(row.get("volume_ratio")) or 0) * 8, 20)
    trend_bonus = 12 if (safe_float(row.get("ma_short")) or 0) > (safe_float(row.get("ma_long")) or 0) else 0
    turnover = min((safe_float(row.get("turnover_rate")) or 0) * 1.5, 12)
    amplitude_penalty = min((safe_float(row.get("amplitude")) or 0) * 40, 8)
    return _with_strategy_rule_adjustment(
        float(rps) * 0.65 + volume_ratio + trend_bonus + turnover - amplitude_penalty + theme_bonus,
        row,
        strategy,
    )


def _score_breakdown(row: Dict[str, Any], strategy: Dict[str, Any]) -> Dict[str, float]:
    feature_engines = _feature_engines(strategy)
    rps = safe_float(row.get(f"rps{int(strategy.get('rps_window') or 20)}")) or safe_float(row.get("rps20")) or 0.0
    amount = safe_float(row.get("amount")) or 0.0
    min_amount = safe_float(strategy.get("min_amount")) or 0.0
    turnover = safe_float(row.get("turnover_rate")) or 0.0
    pct_chg = safe_float(row.get("pct_chg")) or 0.0
    amplitude = safe_float(row.get("amplitude")) or 0.0
    ma_distance = safe_float(row.get("ma_distance"))

    volume = 0.0
    if min_amount > 0:
        volume += min(amount / min_amount, 2.0) * 4
    volume += min((safe_float(row.get("volume_ratio")) or 0.0) * 4, 10)
    volume += min(turnover * 0.8, 6)

    trend = min(float(rps) * 0.22, 22)
    if (safe_float(row.get("ma_short")) or 0) > (safe_float(row.get("ma_long")) or 0):
        trend += 8
    if (safe_float(row.get("macd_dif")) or 0) > (safe_float(row.get("macd_dea")) or 0):
        trend += 5

    position = 8.0
    if ma_distance is not None:
        position += max(0.0, 10 - min(abs(ma_distance) * 100, 10))

    pattern = 0.0
    freshness = 0.0
    risk = 0.0
    theme = max(_theme_score_bonus(row, strategy), 0.0)

    if "platform_breakout" in feature_engines:
        platform_range = safe_float(row.get("platform_range"))
        breakout_clearance = safe_float(row.get("platform_breakout_clearance"))
        breakout_volume = safe_float(row.get("platform_breakout_volume_ratio"))
        bull_volume = safe_float(row.get("platform_bull_volume_ratio"))
        bullish_ratio = safe_float(row.get("platform_bullish_ratio"))
        body_strength = safe_float(row.get("platform_body_strength"))
        max_range = safe_float(strategy.get("platform_max_range")) or 0.12
        min_clearance = safe_float(strategy.get("platform_breakout_clearance")) or 0.0
        max_clearance = safe_float(strategy.get("platform_breakout_max_clearance")) or 0.08

        if breakout_clearance is not None:
            position += _band_score(breakout_clearance, min_clearance, max_clearance, 14)
            freshness += _band_score(breakout_clearance, min_clearance, max_clearance, 12)
            if breakout_clearance > max_clearance:
                risk += min((breakout_clearance - max_clearance) * 180, 16)
        if platform_range is not None:
            pattern += max(0.0, (max_range - platform_range) / max_range) * 12 if platform_range <= max_range else 0
            if platform_range > max_range:
                risk += min((platform_range - max_range) * 80, 8)
        if bullish_ratio is not None:
            pattern += min(bullish_ratio * 10, 8)
        if body_strength is not None:
            pattern += min(body_strength * 4, 8)
        if row.get("platform_breakout_bullish"):
            pattern += 5
        if breakout_volume is not None:
            volume += min(breakout_volume * 5, 18)
        if bull_volume is not None:
            volume += min(bull_volume * 5, 8)
        if row.get("platform_first_breakout"):
            freshness += 12
        elif _condition_mode(strategy, "platform_breakout_first_mode", "score") != "off":
            risk += 8
        recent_gain = safe_float(row.get("platform_recent_gain_5d"))
        if recent_gain is not None:
            freshness += max(0.0, 8 - min(max(recent_gain, 0.0) * 60, 8))
            if recent_gain > 0.12:
                risk += min((recent_gain - 0.12) * 100, 12)
        if row.get("platform_ma_bullish"):
            trend += 6
        if row.get("platform_ma_rising"):
            trend += 6

    elif "platform_setup" in feature_engines:
        setup_range = safe_float(row.get("platform_setup_range"))
        distance_to_high = safe_float(row.get("platform_setup_distance_to_high"))
        volume_contraction = safe_float(row.get("platform_setup_volume_contraction"))
        bull_volume = safe_float(row.get("platform_setup_bull_volume_ratio"))
        recent_gain = safe_float(row.get("platform_setup_recent_gain_5d"))
        ma_convergence = safe_float(row.get("platform_setup_ma_convergence"))
        max_range = safe_float(strategy.get("platform_setup_max_range")) or 0.12
        max_distance = safe_float(strategy.get("platform_setup_max_distance_to_high")) or 0.035

        if setup_range is not None:
            pattern += max(0.0, (max_range - setup_range) / max_range) * 16 if setup_range <= max_range else 0
            if setup_range > max_range:
                risk += min((setup_range - max_range) * 70, 8)
        if distance_to_high is not None:
            position += max(0.0, (max_distance - distance_to_high) / max_distance) * 16 if distance_to_high <= max_distance else 0
            freshness += max(0.0, (max_distance - distance_to_high) / max_distance) * 12 if distance_to_high <= max_distance else 0
        if volume_contraction is not None:
            volume += max(0.0, (1.2 - volume_contraction) / 1.2) * 8 if volume_contraction <= 1.2 else 0
        if bull_volume is not None:
            volume += min(bull_volume * 5, 9)
        if recent_gain is not None:
            freshness += 10 if recent_gain <= (safe_float(strategy.get("platform_setup_max_recent_gain_5d")) or 0.1) else 0
            if recent_gain > 0.12:
                risk += min((recent_gain - 0.12) * 100, 12)
        if ma_convergence is not None:
            pattern += max(0.0, (0.08 - ma_convergence) / 0.08) * 8 if ma_convergence <= 0.08 else 0
        if row.get("platform_setup_ma_turning_up"):
            trend += 6

    elif "trend_resonance" in feature_engines:
        if row.get("trend_price_above_ema_long"):
            trend += 8
        if row.get("trend_ema_long_rising"):
            trend += 8
        if row.get("trend_ema_fast_above_mid"):
            trend += 6
        if row.get("trend_macd_dif_above_dea"):
            trend += 7
        if row.get("trend_stoch_k_above_d"):
            trend += 5
        distance = safe_float(row.get("trend_ema_mid_distance"))
        if distance is not None:
            position += max(0.0, (0.12 - max(distance, 0.0)) / 0.12) * 12 if distance <= 0.12 else 0
            if distance > 0.12:
                risk += min((distance - 0.12) * 90, 14)
        recent_gain = safe_float(row.get("trend_recent_gain_10d"))
        if recent_gain is not None:
            freshness += 10 if recent_gain <= (safe_float(strategy.get("trend_max_recent_gain_10d")) or 0.28) else 0
            if recent_gain > 0.28:
                risk += min((recent_gain - 0.28) * 70, 14)
        if row.get("trend_thunder_signal") or row.get("trend_follow_signal") or row.get("trend_stealth_signal"):
            pattern += 10
        if row.get("trend_stoch_overheated"):
            risk += 8
    else:
        if ma_distance is not None:
            position += max(0.0, 8 - min(max(ma_distance, 0.0) * 80, 8))
        pattern += max(0.0, 10 - min(amplitude * 60, 10))
        freshness += max(0.0, 8 - min(abs(pct_chg) * 0.8, 8))

    max_pct_chg = safe_float(strategy.get("max_pct_chg"))
    if max_pct_chg is not None and pct_chg > max_pct_chg:
        risk += min((pct_chg - max_pct_chg) * 1.5, 10)
    if amplitude > 0:
        risk += min(amplitude * 18, 8)

    return {
        "position": round(max(position, 0.0), 2),
        "volume": round(max(volume, 0.0), 2),
        "pattern": round(max(pattern, 0.0), 2),
        "trend": round(max(trend, 0.0), 2),
        "theme": round(theme, 2),
        "freshness": round(max(freshness, 0.0), 2),
        "risk": round(-max(risk, 0.0), 2),
        "custom_rules": _strategy_rule_score_adjustment(row, strategy),
        "resonance_bonus": _strategy_resonance_bonus(row, strategy),
    }


def _freshness_metrics(row: Dict[str, Any], strategy: Dict[str, Any]) -> Dict[str, Optional[float]]:
    feature_engines = _feature_engines(strategy)
    if "platform_setup" in feature_engines:
        distance = safe_float(row.get("platform_setup_distance_to_high"))
        return {
            "first_breakout_days": None,
            "days_above_platform": None,
            "distance_to_platform_upper": _round_optional(distance, 6),
            "breakout_clearance": None,
            "recent_gain_5d": _round_optional(safe_float(row.get("platform_setup_recent_gain_5d")), 6),
            "ma_distance": _round_optional(safe_float(row.get("ma_distance")), 6),
        }
    if "platform_breakout" in feature_engines:
        clearance = safe_float(row.get("platform_breakout_clearance"))
        first_breakout_days = safe_float(row.get("platform_first_breakout_days"))
        if first_breakout_days is None and row.get("platform_first_breakout"):
            first_breakout_days = 0.0
        return {
            "first_breakout_days": first_breakout_days,
            "days_above_platform": safe_float(row.get("platform_days_above_upper")),
            "distance_to_platform_upper": _round_optional(-clearance if clearance is not None else None, 6),
            "breakout_clearance": _round_optional(clearance, 6),
            "recent_gain_5d": _round_optional(safe_float(row.get("platform_recent_gain_5d")), 6),
            "ma_distance": _round_optional(safe_float(row.get("ma_distance")), 6),
        }
    if "trend_resonance" in feature_engines:
        return {
            "first_breakout_days": None,
            "days_above_platform": None,
            "distance_to_platform_upper": None,
            "breakout_clearance": None,
            "recent_gain_5d": _round_optional(safe_float(row.get("trend_recent_gain_10d")), 6),
            "ma_distance": _round_optional(safe_float(row.get("trend_ema_mid_distance")), 6),
        }
    return {
        "first_breakout_days": None,
        "days_above_platform": None,
        "distance_to_platform_upper": None,
        "breakout_clearance": None,
        "recent_gain_5d": None,
        "ma_distance": _round_optional(safe_float(row.get("ma_distance")), 6),
    }


def _candidate_interpretation(row: Dict[str, Any], strategy: Dict[str, Any]) -> Dict[str, Any]:
    breakdown = row.get("score_breakdown") if isinstance(row.get("score_breakdown"), dict) else {}
    freshness = row.get("freshness") if isinstance(row.get("freshness"), dict) else {}
    freshness_label = _freshness_label(row, strategy, freshness)
    strengths = _interpretation_strengths(row, strategy, breakdown, freshness_label)
    risks = _interpretation_risks(row, strategy, breakdown, freshness)
    trade_read = _trade_read(freshness_label, risks)
    conclusion = _interpretation_conclusion(freshness_label, trade_read, strengths, risks)
    return {
        "freshness_label": freshness_label,
        "trade_read": trade_read,
        "conclusion": conclusion,
        "strengths": strengths[:4],
        "risks": risks[:4],
    }


def _freshness_label(row: Dict[str, Any], strategy: Dict[str, Any], freshness: Dict[str, Any]) -> str:
    feature_engines = _feature_engines(strategy)
    if "platform_setup" in feature_engines:
        distance = safe_float(freshness.get("distance_to_platform_upper"))
        if distance is not None and distance <= 0.02:
            return "临界贴近"
        return "临界观察"
    if "platform_breakout" in feature_engines:
        first_days = safe_float(freshness.get("first_breakout_days"))
        days_above = safe_float(freshness.get("days_above_platform"))
        clearance = safe_float(freshness.get("breakout_clearance"))
        recent_gain = safe_float(freshness.get("recent_gain_5d"))
        max_clearance = safe_float(strategy.get("platform_breakout_max_clearance")) or 0.08
        if first_days == 0:
            return "首日突破"
        if first_days is not None and first_days <= 2:
            return "二次确认"
        if (
            (days_above is not None and days_above >= 4)
            or (clearance is not None and clearance > max_clearance)
            or (recent_gain is not None and recent_gain > 0.12)
        ):
            return "已走远"
        return "突破延续"
    if "trend_resonance" in feature_engines:
        recent_gain = safe_float(freshness.get("recent_gain_5d"))
        if recent_gain is not None and recent_gain > 0.2:
            return "强势后段"
        return "强势确认"
    return "趋势观察"


def _interpretation_strengths(
    row: Dict[str, Any],
    strategy: Dict[str, Any],
    breakdown: Dict[str, Any],
    freshness_label: str,
) -> List[str]:
    strengths: List[str] = []
    if (safe_float(breakdown.get("volume")) or 0) >= 18:
        strengths.append("量能确认度高，成交额与放量同时支撑信号。")
    elif (safe_float(row.get("amount")) or 0) >= (safe_float(strategy.get("min_amount")) or 0):
        strengths.append("量能达到策略门槛，具备基本成交活跃度。")
    if freshness_label in {"首日突破", "临界贴近", "临界观察"}:
        strengths.append(f"新鲜度较好，当前属于{freshness_label}。")
    if (safe_float(breakdown.get("pattern")) or 0) >= 15:
        strengths.append("形态完成度较高，平台或K线结构比较清晰。")
    if (safe_float(breakdown.get("trend")) or 0) >= 25:
        strengths.append("趋势背景较强，RPS、均线或 MACD 对信号有加分。")
    if row.get("platform_ma_bullish") or row.get("trend_ema_fast_above_mid"):
        strengths.append("短中期均线结构偏多，趋势阻力相对较小。")
    if not strengths:
        strengths.append("综合条件尚可，主要依靠总分排序进入候选。")
    return strengths


def _interpretation_risks(
    row: Dict[str, Any],
    strategy: Dict[str, Any],
    breakdown: Dict[str, Any],
    freshness: Dict[str, Any],
) -> List[str]:
    risks: List[str] = []
    risk_score = abs(safe_float(breakdown.get("risk")) or 0)
    clearance = safe_float(freshness.get("breakout_clearance"))
    recent_gain = safe_float(freshness.get("recent_gain_5d"))
    pct_chg = safe_float(row.get("pct_chg"))
    max_clearance = safe_float(strategy.get("platform_breakout_max_clearance")) or 0.08
    if risk_score >= 10:
        risks.append("风险扣分偏高，可能存在追高或短线过热。")
    if clearance is not None and clearance > max_clearance:
        risks.append(f"已高出平台上沿 {clearance * 100:.2f}%，买点可能偏后。")
    if recent_gain is not None and recent_gain > 0.12:
        risks.append(f"近5日涨幅 {recent_gain * 100:.2f}%，需要防止短线兑现。")
    if pct_chg is not None and pct_chg >= 8:
        risks.append(f"当日涨幅 {pct_chg:.2f}%，次日波动风险会放大。")
    if safe_float(row.get("turnover_rate")) is None:
        risks.append("换手率缺失，量价判断少一层确认。")
    if safe_float(row.get("float_market_value")) is None:
        risks.append("流通市值缺失，规模过滤按策略降级处理。")
    if not risks:
        risks.append("暂未发现明显过热项，仍需结合盘口与大盘环境确认。")
    return risks


def _trade_read(freshness_label: str, risks: List[str]) -> str:
    if freshness_label in {"临界贴近", "临界观察"}:
        return "可观察"
    if freshness_label in {"首日突破", "二次确认"} and not any("偏高" in risk or "偏后" in risk for risk in risks):
        return "可确认"
    if freshness_label == "已走远":
        return "偏追高"
    return "谨慎确认"


def _interpretation_conclusion(
    freshness_label: str,
    trade_read: str,
    strengths: List[str],
    risks: List[str],
) -> str:
    lead = strengths[0].rstrip("。") if strengths else "综合分进入候选"
    risk = risks[0].rstrip("。") if risks else "暂无明显风险"
    return f"{freshness_label}，{trade_read}。{lead}；{risk}。"


def _band_score(value: float, lower: float, upper: float, score: float) -> float:
    if upper <= lower:
        return score if value >= lower else 0.0
    if value < lower:
        return max(0.0, value / lower) * score if lower > 0 else 0.0
    if value <= upper:
        midpoint = lower + (upper - lower) * 0.35
        distance = abs(value - midpoint) / max(upper - lower, 0.000001)
        return max(0.0, score * (1 - distance * 0.75))
    return 0.0


def _candidate_reasons(row: Dict[str, Any], strategy: Dict[str, Any]) -> List[str]:
    reasons = []
    feature_engines = _feature_engines(strategy)
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
    if "platform_setup" in feature_engines:
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
    if "platform_breakout" in feature_engines:
        platform_range = safe_float(row.get("platform_range"))
        if platform_range is not None:
            reasons.append(f"平台振幅 {platform_range * 100:.2f}%")
        breakout_clearance = safe_float(row.get("platform_breakout_clearance"))
        if breakout_clearance is not None:
            reasons.append(f"突破上沿 {breakout_clearance * 100:.2f}%")
        if row.get("platform_first_breakout"):
            reasons.append("首次突破确认")
        elif _condition_mode(strategy, "platform_breakout_first_mode", "score") != "off":
            reasons.append("非首次突破，按策略计分")
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
    if "trend_resonance" in feature_engines:
        ema_fast = safe_float(row.get("trend_ema_fast"))
        ema_mid = safe_float(row.get("trend_ema_mid"))
        ema_long = safe_float(row.get("trend_ema_long"))
        if ema_fast is not None and ema_mid is not None and ema_long is not None:
            reasons.append(
                f"EMA{strategy.get('trend_ema_fast_window')}/"
                f"{strategy.get('trend_ema_mid_window')}/"
                f"EMA{strategy.get('trend_ema_long_window')} {ema_fast:.2f}/{ema_mid:.2f}/{ema_long:.2f}"
            )
        distance = safe_float(row.get("trend_ema_mid_distance"))
        if distance is not None:
            reasons.append(f"距 EMA21 {distance * 100:.2f}%")
        macd_dif = safe_float(row.get("trend_macd_dif"))
        macd_dea = safe_float(row.get("trend_macd_dea"))
        if macd_dif is not None and macd_dea is not None:
            reasons.append(f"MACD DIF/DEA {macd_dif:.3f}/{macd_dea:.3f}")
        stoch_k = safe_float(row.get("trend_stoch_k"))
        stoch_d = safe_float(row.get("trend_stoch_d"))
        if stoch_k is not None and stoch_d is not None:
            reasons.append(f"随机指标 K/D {stoch_k:.1f}/{stoch_d:.1f}")
        recent_gain = safe_float(row.get("trend_recent_gain_10d"))
        if recent_gain is not None:
            reasons.append(f"近10日涨幅 {recent_gain * 100:.2f}%")
        label = row.get("trend_signal_label")
        if label:
            reasons.append(str(label))
    for resonance in _matching_strategy_resonances(row, strategy):
        bonus = safe_float(resonance.get("bonus"))
        if bonus is not None and bonus > 0:
            reasons.append(f"{resonance.get('name') or '组合共振'} +{bonus:g}分")
    return reasons


def _zero_reason(funnel: List[Dict[str, Any]]) -> str:
    if not funnel:
        return "本地仓库暂无可分析行情，请先更新数据。"
    largest = max(funnel, key=lambda item: item.get("removed_count", 0))
    if largest.get("removed_count", 0) <= 0:
        return "没有股票同时满足当前策略，请放宽指标或更新更多历史数据。"
    return f"主要卡在“{largest['step_name']}”：该层过滤掉 {largest['removed_count']} 只股票。"


def _emit_analysis_progress(progress: Optional[AnalysisProgress], stage: str, processed: int) -> None:
    if progress:
        progress(stage, processed, ANALYSIS_TOTAL_STEPS)


class AnalysisService:
    def __init__(self, db: Database):
        self.db = db

    def run(self, config: Dict[str, Any], progress: Optional[AnalysisProgress] = None) -> str:
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
            rows = self._build_analysis_frame(strategy, progress=progress)
            _emit_analysis_progress(progress, "应用策略条件", 5)
            if rows.empty:
                candidates, funnel, zero_reason = [], [], _zero_reason([])
            else:
                candidates, funnel, zero_reason = apply_strategy_filters(rows, strategy)
            _emit_analysis_progress(progress, "保存分析报告", 6)
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

    def _build_analysis_frame(
        self,
        strategy: Dict[str, Any],
        as_of_date: Optional[date] = None,
        progress: Optional[AnalysisProgress] = None,
    ) -> pd.DataFrame:
        target_date = _date_value(as_of_date) if as_of_date else None
        _emit_analysis_progress(progress, "读取本地行情", 1)
        if target_date:
            bars = pd.DataFrame(
                self.db.query(
                    """
                    SELECT h.*, b.name, b.suspended
                    FROM historical_bars h
                    LEFT JOIN stock_basic b USING (code)
                    WHERE h.date >= ? AND h.date <= ?
                    ORDER BY h.code, h.date
                    """,
                    [target_date - timedelta(days=380), target_date],
                )
            )
        else:
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
        _emit_analysis_progress(progress, "合并快照与市值", 2)
        if target_date:
            snapshots = pd.DataFrame()
            if strategy.get("_backtest_float_market_value_policy") == "latest_proxy":
                float_values = pd.DataFrame(
                    self.db.query(
                        """
                        SELECT *
                        FROM (
                            SELECT *,
                                   ROW_NUMBER() OVER (
                                       PARTITION BY code
                                       ORDER BY
                                           CASE WHEN date <= ? THEN 0 ELSE 1 END,
                                           date DESC
                                   ) AS row_num
                            FROM float_market_values
                        )
                        WHERE row_num = 1
                        """,
                        [target_date],
                    )
                )
            else:
                float_values = pd.DataFrame(
                    self.db.query(
                        """
                        SELECT *
                        FROM (
                            SELECT *,
                                   ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) AS row_num
                            FROM float_market_values
                            WHERE date <= ?
                        )
                        WHERE row_num = 1
                        """,
                        [target_date],
                    )
                )
        else:
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
        _emit_analysis_progress(progress, "计算相对强弱", 3)
        rps_scores = compute_rps_scores(bars[["code", "date", "close"]], windows=(20, 60, 120))
        _emit_analysis_progress(progress, "计算技术形态", 4)
        output = []
        analysis_engines = set(strategy.get("analysis_engines") or [])
        for code, group in bars.groupby("code"):
            group = group.sort_values("date")
            latest_bar = group.iloc[-1].to_dict()
            if target_date and _date_value(latest_bar.get("date")) != target_date:
                continue
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
            if "platform_setup" in analysis_engines:
                platform_metrics.update(compute_platform_setup_metrics(group, strategy))
            if "trend_resonance" in analysis_engines:
                platform_metrics.update(compute_trend_resonance_metrics(group, strategy))
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
        frame = self._enrich_tushare_features(pd.DataFrame(output), target_date)
        return self._enrich_theme_metrics(frame, target_date)

    def _enrich_tushare_features(self, frame: pd.DataFrame, as_of_date: Optional[date] = None) -> pd.DataFrame:
        if frame.empty or "code" not in frame:
            return frame
        enriched = frame.copy()
        if "feature_dates" not in enriched.columns:
            enriched["feature_dates"] = [{} for _ in range(len(enriched))]
        daily_basic = _records_by_code(self._latest_tushare_rows("tushare_daily_basic", as_of_date))
        moneyflow = _records_by_code(self._latest_tushare_rows("tushare_moneyflow", as_of_date))
        limits = _records_by_code(self._latest_tushare_rows("tushare_limit_list_d", as_of_date))
        cyq_perf = _records_by_code(self._latest_tushare_rows("tushare_cyq_perf", as_of_date))
        top_list = _records_by_code(self._latest_top_list_rows(as_of_date))
        top_inst = _records_by_code(self._latest_sum_rows("tushare_top_inst", "net_buy", "top_inst_net_buy", as_of_date))
        hot_money = _records_by_code(self._latest_sum_rows("tushare_hm_detail", "net_amount", "hot_money_net_amount", as_of_date))
        chips = _records_by_code(self._latest_chip_rows(as_of_date))

        for index, row in enriched.iterrows():
            code = str(row.get("code"))
            sources = dict(row.get("data_sources") or {})
            feature_dates = dict(row.get("feature_dates") or {})

            daily = daily_basic.get(code)
            if daily:
                _assign_first_number(enriched, index, "turnover_rate", daily.get("turnover_rate"))
                _assign_first_number(enriched, index, "volume_ratio", daily.get("volume_ratio"))
                _assign_first_number(enriched, index, "float_market_value", daily.get("circ_mv"))
                _assign_first_number(enriched, index, "total_market_value", daily.get("total_mv"))
                _assign_first_number(enriched, index, "pe", daily.get("pe"))
                _assign_first_number(enriched, index, "pb", daily.get("pb"))
                sources["daily_basic"] = daily.get("source") or "Tushare daily_basic"
                feature_dates["daily_basic"] = _date_text(daily.get("trade_date"))

            flow = moneyflow.get(code)
            if flow:
                _assign_first_number(enriched, index, "main_net_amount", flow.get("main_net_amount"))
                _assign_first_number(enriched, index, "net_mf_amount", flow.get("net_mf_amount"))
                large = _subtract_optional(flow.get("buy_lg_amount"), flow.get("sell_lg_amount"))
                super_large = _subtract_optional(flow.get("buy_elg_amount"), flow.get("sell_elg_amount"))
                medium = _subtract_optional(flow.get("buy_md_amount"), flow.get("sell_md_amount"))
                small = _subtract_optional(flow.get("buy_sm_amount"), flow.get("sell_sm_amount"))
                _assign_first_number(enriched, index, "large_net_amount", large)
                _assign_first_number(enriched, index, "super_large_net_amount", super_large)
                _assign_first_number(enriched, index, "medium_net_amount", medium)
                _assign_first_number(enriched, index, "small_net_amount", small)
                amount = safe_float(row.get("amount"))
                main = safe_float(flow.get("main_net_amount"))
                if main is not None and amount is not None and amount > 0:
                    enriched.at[index, "main_net_amount_ratio"] = _round_optional(main / amount, 6)
                sources["moneyflow"] = flow.get("source") or "Tushare moneyflow"
                feature_dates["moneyflow"] = _date_text(flow.get("trade_date"))

            limit_row = limits.get(code)
            if limit_row:
                enriched.at[index, "limit_type"] = limit_row.get("limit_type")
                _assign_first_number(enriched, index, "limit_open_times", limit_row.get("open_times"))
                _assign_first_number(enriched, index, "limit_fd_amount", limit_row.get("fd_amount"))
                fd_amount = safe_float(limit_row.get("fd_amount"))
                float_mv = safe_float(enriched.at[index, "float_market_value"]) if "float_market_value" in enriched else None
                if fd_amount is not None and float_mv is not None and float_mv > 0:
                    enriched.at[index, "limit_fd_mv_ratio"] = _round_optional(fd_amount / float_mv, 6)
                sources["limit_event"] = limit_row.get("source") or "Tushare limit_list_d"
                feature_dates["limit_event"] = _date_text(limit_row.get("trade_date"))

            cyq = cyq_perf.get(code)
            if cyq:
                _assign_first_number(enriched, index, "cyq_winner_rate", cyq.get("winner_rate"))
                _assign_first_number(enriched, index, "cost_15pct", cyq.get("cost_15pct"))
                _assign_first_number(enriched, index, "cost_50pct", cyq.get("cost_50pct"))
                _assign_first_number(enriched, index, "cost_85pct", cyq.get("cost_85pct"))
                latest_price = safe_float(row.get("latest_price"))
                cost_50 = safe_float(cyq.get("cost_50pct"))
                cost_15 = safe_float(cyq.get("cost_15pct"))
                cost_85 = safe_float(cyq.get("cost_85pct"))
                if latest_price is not None and cost_50 is not None and cost_50 > 0:
                    enriched.at[index, "price_to_cost_50pct"] = _round_optional((latest_price - cost_50) / cost_50, 6)
                if cost_15 is not None and cost_85 is not None and cost_50 is not None and cost_50 > 0:
                    enriched.at[index, "cost_width_15_85"] = _round_optional((cost_85 - cost_15) / cost_50, 6)
                sources["cyq_perf"] = cyq.get("source") or "Tushare cyq_perf"
                feature_dates["cyq_perf"] = _date_text(cyq.get("trade_date"))

            chip = chips.get(code)
            if chip:
                _assign_first_number(enriched, index, "cyq_chip_peak_percent", chip.get("cyq_chip_peak_percent"))
                _assign_first_number(enriched, index, "cyq_chip_price_span", chip.get("cyq_chip_price_span"))
                sources["cyq_chips"] = chip.get("source") or "Tushare cyq_chips"
                feature_dates["cyq_chips"] = _date_text(chip.get("trade_date"))

            top = top_list.get(code)
            if top:
                _assign_first_number(enriched, index, "top_list_net_amount", top.get("top_list_net_amount"))
                _assign_first_number(enriched, index, "top_list_amount_rate", top.get("top_list_amount_rate"))
                enriched.at[index, "top_list_reason"] = top.get("top_list_reason")
                sources["top_list"] = top.get("source") or "Tushare top_list"
                feature_dates["top_list"] = _date_text(top.get("trade_date"))

            inst = top_inst.get(code)
            if inst:
                _assign_first_number(enriched, index, "top_inst_net_buy", inst.get("top_inst_net_buy"))
                sources["top_inst"] = inst.get("source") or "Tushare top_inst"
                feature_dates["top_inst"] = _date_text(inst.get("trade_date"))

            hot = hot_money.get(code)
            if hot:
                _assign_first_number(enriched, index, "hot_money_net_amount", hot.get("hot_money_net_amount"))
                sources["hot_money"] = hot.get("source") or "Tushare hm_detail"
                feature_dates["hot_money"] = _date_text(hot.get("trade_date"))

            enriched.at[index, "data_sources"] = sources
            enriched.at[index, "feature_dates"] = feature_dates
        return enriched

    def _latest_tushare_rows(self, table: str, as_of_date: Optional[date] = None) -> List[Dict[str, Any]]:
        where = "WHERE trade_date <= ?" if as_of_date else ""
        params: List[Any] = [as_of_date] if as_of_date else []
        return self.db.query(
            f"""
            SELECT *
            FROM (
                SELECT *,
                       ROW_NUMBER() OVER (PARTITION BY code ORDER BY trade_date DESC) AS row_num
                FROM {table}
                {where}
            )
            WHERE row_num = 1
            """,
            params,
        )

    def _latest_sum_rows(
        self,
        table: str,
        value_column: str,
        output_column: str,
        as_of_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        where = "WHERE trade_date <= ?" if as_of_date else ""
        params: List[Any] = [as_of_date] if as_of_date else []
        return self.db.query(
            f"""
            WITH latest AS (
                SELECT code, MAX(trade_date) AS trade_date
                FROM {table}
                {where}
                GROUP BY code
            )
            SELECT t.code,
                   t.trade_date,
                   SUM(t.{value_column}) AS {output_column},
                   MAX(t.source) AS source
            FROM {table} t
            JOIN latest l ON l.code = t.code AND l.trade_date = t.trade_date
            GROUP BY t.code, t.trade_date
            """,
            params,
        )

    def _latest_top_list_rows(self, as_of_date: Optional[date] = None) -> List[Dict[str, Any]]:
        where = "WHERE trade_date <= ?" if as_of_date else ""
        params: List[Any] = [as_of_date] if as_of_date else []
        return self.db.query(
            f"""
            WITH latest AS (
                SELECT code, MAX(trade_date) AS trade_date
                FROM tushare_top_list
                {where}
                GROUP BY code
            )
            SELECT t.code,
                   t.trade_date,
                   SUM(t.net_amount) AS top_list_net_amount,
                   MAX(t.amount_rate) AS top_list_amount_rate,
                   string_agg(COALESCE(t.reason, ''), ' / ') AS top_list_reason,
                   MAX(t.source) AS source
            FROM tushare_top_list t
            JOIN latest l ON l.code = t.code AND l.trade_date = t.trade_date
            GROUP BY t.code, t.trade_date
            """,
            params,
        )

    def _latest_chip_rows(self, as_of_date: Optional[date] = None) -> List[Dict[str, Any]]:
        where = "WHERE trade_date <= ?" if as_of_date else ""
        params: List[Any] = [as_of_date] if as_of_date else []
        return self.db.query(
            f"""
            WITH latest AS (
                SELECT code, MAX(trade_date) AS trade_date
                FROM tushare_cyq_chips
                {where}
                GROUP BY code
            )
            SELECT c.code,
                   c.trade_date,
                   MAX(c.percent) AS cyq_chip_peak_percent,
                   MAX(c.price) - MIN(c.price) AS cyq_chip_price_span,
                   MAX(c.source) AS source
            FROM tushare_cyq_chips c
            JOIN latest l ON l.code = c.code AND l.trade_date = c.trade_date
            GROUP BY c.code, c.trade_date
            """,
            params,
        )

    def _enrich_theme_metrics(self, frame: pd.DataFrame, as_of_date: Optional[date] = None) -> pd.DataFrame:
        if frame.empty or "code" not in frame:
            return frame
        enriched = frame.copy()
        enriched["concept_count"] = 0
        enriched["topic_count"] = 0
        enriched["theme_limit_count"] = 0
        enriched["topic_heat"] = 0.0
        codes = {str(code) for code in enriched["code"].dropna().tolist()}
        if not codes:
            return enriched
        members = [
            row
            for row in self.db.query(
                """
                SELECT code, con_code
                FROM tushare_ths_member
                WHERE code IS NOT NULL AND con_code IS NOT NULL
                """
            )
            if str(row.get("code")) in codes
        ]
        if not members:
            return enriched

        themes_by_code: Dict[str, set[str]] = {}
        codes_by_theme: Dict[str, set[str]] = {}
        for row in members:
            code = str(row.get("code"))
            theme = str(row.get("con_code"))
            themes_by_code.setdefault(code, set()).add(theme)
            codes_by_theme.setdefault(theme, set()).add(code)

        limit_codes: set[str] = set()
        latest_limit_date = (
            self.db.scalar("SELECT MAX(trade_date) FROM tushare_limit_list_d WHERE trade_date <= ?", [as_of_date])
            if as_of_date
            else self.db.scalar("SELECT MAX(trade_date) FROM tushare_limit_list_d")
        )
        if latest_limit_date:
            for row in self.db.query(
                """
                SELECT code, limit_type
                FROM tushare_limit_list_d
                WHERE trade_date = ?
                """,
                [latest_limit_date],
            ):
                limit_type = str(row.get("limit_type") or "").upper()
                if "U" in limit_type or "UP" in limit_type or "涨停" in limit_type:
                    limit_codes.add(str(row.get("code")))

        frame_by_code = enriched.set_index("code", drop=False)
        theme_heat: Dict[str, float] = {}
        theme_limit_counts: Dict[str, int] = {}
        for theme, member_codes in codes_by_theme.items():
            present_codes = [code for code in member_codes if code in frame_by_code.index]
            if not present_codes:
                continue
            subset = frame_by_code.loc[present_codes]
            if isinstance(subset, pd.Series):
                subset = subset.to_frame().T
            pct = pd.to_numeric(subset.get("pct_chg"), errors="coerce")
            rps = pd.to_numeric(subset.get("rps20"), errors="coerce")
            positive_ratio = float((pct > 0).mean()) if len(pct) else 0.0
            strong_ratio = float((rps >= 70).mean()) if len(rps) else 0.0
            limit_count = len(member_codes & limit_codes)
            theme_limit_counts[theme] = limit_count
            avg_pct = max(float(pct.fillna(0).mean()) if len(pct) else 0.0, 0.0)
            heat = positive_ratio * 35 + strong_ratio * 35 + min(limit_count, 5) * 6 + min(avg_pct, 10) * 2
            theme_heat[theme] = round(min(100.0, heat), 2)

        for index, row in enriched.iterrows():
            code = str(row.get("code"))
            themes = themes_by_code.get(code, set())
            enriched.at[index, "concept_count"] = len(themes)
            enriched.at[index, "topic_count"] = len(themes)
            if themes:
                enriched.at[index, "theme_limit_count"] = max((theme_limit_counts.get(theme, 0) for theme in themes), default=0)
                enriched.at[index, "topic_heat"] = max((theme_heat.get(theme, 0.0) for theme in themes), default=0.0)
        return enriched

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


def _assign_first_number(frame: pd.DataFrame, index: Any, column: str, value: Any) -> None:
    parsed = safe_float(value)
    if parsed is not None:
        frame.at[index, column] = parsed


def _subtract_optional(left: Any, right: Any) -> Optional[float]:
    left_value = safe_float(left)
    right_value = safe_float(right)
    if left_value is None or right_value is None:
        return None
    return left_value - right_value


def _records_by_code(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(row.get("code")): row for row in rows if row.get("code")}


def _date_text(value: Any) -> Optional[str]:
    parsed = _date_value(value)
    return parsed.isoformat() if parsed else None


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


def _date_value(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])
