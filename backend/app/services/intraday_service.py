from __future__ import annotations

import json
import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from backend.app.db import Database
from backend.app.services.market_utils import safe_float


DEFAULT_INTRADAY_RADAR_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "platform_lookback_days": 20,
    "platform_max_range": 0.12,
    "near_upper_distance": 0.03,
    "breakout_min_clearance": 0.0,
    "breakout_max_clearance": 0.08,
    "max_pct_chg": 8.0,
    "min_amount": 50_000_000,
    "min_intraday_amount_ratio": 0.15,
    "candidate_limit": 80,
    "require_ma_bullish": False,
    "require_macd_strong": False,
    "include_bj": False,
    "exclude_star_board": False,
}


class IntradayRadarService:
    def __init__(self, db: Database):
        self.db = db

    def get_config(self) -> Dict[str, Any]:
        row = self.db.query("SELECT config_json FROM intraday_radar_config WHERE id = 'default'")
        if not row:
            config = normalize_intraday_config(DEFAULT_INTRADAY_RADAR_CONFIG)
            self.save_config(config)
            return config
        return normalize_intraday_config(json.loads(row[0]["config_json"] or "{}"))

    def save_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        normalized = normalize_intraday_config(config)
        self.db.upsert(
            "intraday_radar_config",
            [
                {
                    "id": "default",
                    "config_json": json.dumps(normalized, ensure_ascii=False),
                    "updated_at": datetime.utcnow(),
                }
            ],
            ["id"],
        )
        return normalized

    def record_snapshots(
        self,
        frame: pd.DataFrame,
        sample_at: Optional[datetime] = None,
        trade_date: Optional[str | date] = None,
    ) -> int:
        if frame is None or frame.empty:
            return 0
        sample_time = sample_at or datetime.utcnow()
        target_date = _date_value(trade_date) or sample_time.date()
        rows = []
        for item in frame.to_dict("records"):
            code = item.get("code")
            if not code:
                continue
            rows.append(
                {
                    "code": code,
                    "trade_date": target_date,
                    "sample_at": sample_time,
                    "name": item.get("name") or code,
                    "latest_price": safe_float(item.get("latest_price")),
                    "pct_chg": safe_float(item.get("pct_chg")),
                    "high": safe_float(item.get("high")),
                    "low": safe_float(item.get("low")),
                    "volume": safe_float(item.get("volume")),
                    "amount": safe_float(item.get("amount")),
                    "source": item.get("source") or "AkShare 新浪",
                    "created_at": datetime.utcnow(),
                }
            )
        return self.db.upsert("intraday_snapshots", rows, ["code", "sample_at"])

    def run_radar(
        self,
        sample_at: Optional[datetime | str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> int:
        radar_config = normalize_intraday_config(config or self.get_config())
        target_sample = _sample_value(sample_at) or self.db.scalar(
            "SELECT MAX(sample_at) FROM intraday_snapshots"
        )
        if not target_sample:
            return 0
        target_sample_text = _sample_text(target_sample)
        snapshots = self.db.query(
            """
            SELECT s.*, b.is_st, b.suspended
            FROM intraday_snapshots s
            LEFT JOIN stock_basic b ON b.code = s.code
            WHERE s.sample_at = ?
              AND s.latest_price IS NOT NULL
            """,
            [target_sample_text],
        )
        if not snapshots:
            return 0
        trade_date = _date_value(snapshots[0].get("trade_date")) or _sample_value(target_sample).date()
        history = self._history_for_snapshot([row["code"] for row in snapshots], trade_date)
        previous = self._previous_snapshots([row["code"] for row in snapshots], target_sample_text, trade_date)

        rows = []
        for snapshot in snapshots:
            if snapshot.get("is_st") or snapshot.get("suspended"):
                continue
            candidate = self._score_snapshot(snapshot, history.get(snapshot["code"], []), previous.get(snapshot["code"]), radar_config)
            if candidate:
                rows.append(candidate)
        rows.sort(key=lambda row: row["radar_score"], reverse=True)
        limited = rows[: radar_config["candidate_limit"]]
        for index, row in enumerate(limited, start=1):
            row["rank"] = index
        self.db.execute(
            "DELETE FROM intraday_radar_candidates WHERE sample_at = ?",
            [target_sample_text],
            write=True,
        )
        return self.db.upsert("intraday_radar_candidates", limited, ["sample_at", "code"])

    def latest(self, limit: int = 100) -> Dict[str, Any]:
        sample_at = self.db.scalar("SELECT MAX(sample_at) FROM intraday_radar_candidates")
        config = self.get_config()
        if not sample_at:
            latest_sample = self.db.scalar("SELECT MAX(sample_at) FROM intraday_snapshots")
            return {
                "config": config,
                "sample_at": latest_sample,
                "sample_count": self._sample_count(latest_sample),
                "summary": {"candidate_count": 0, "zero_reason": "盘中雷达尚未生成。"},
                "rows": [],
            }
        rows = self.db.query(
            """
            SELECT *
            FROM intraday_radar_candidates
            WHERE sample_at = ?
            ORDER BY rank
            LIMIT ?
            """,
            [_sample_text(sample_at), max(1, min(limit, 500))],
        )
        for row in rows:
            row["reasons"] = json.loads(row.pop("reasons_json") or "[]")
            row["metrics"] = json.loads(row.pop("metrics_json") or "{}")
        return {
            "config": config,
            "sample_at": sample_at,
            "sample_count": self._sample_count(sample_at),
            "summary": {"candidate_count": len(rows)},
            "rows": rows,
        }

    def _history_for_snapshot(self, codes: List[str], trade_date: date) -> Dict[str, List[Dict[str, Any]]]:
        if not codes:
            return {}
        placeholders = ", ".join(["?"] * len(codes))
        rows = self.db.query(
            f"""
            SELECT *
            FROM historical_bars
            WHERE code IN ({placeholders})
              AND date < ?
            ORDER BY code, date
            """,
            codes + [trade_date],
        )
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row["code"], []).append(row)
        return grouped

    def _previous_snapshots(
        self,
        codes: List[str],
        sample_at: str,
        trade_date: date,
    ) -> Dict[str, Dict[str, Any]]:
        if not codes:
            return {}
        placeholders = ", ".join(["?"] * len(codes))
        rows = self.db.query(
            f"""
            SELECT *
            FROM intraday_snapshots
            WHERE code IN ({placeholders})
              AND trade_date = ?
              AND sample_at < ?
            QUALIFY ROW_NUMBER() OVER (PARTITION BY code ORDER BY sample_at DESC) = 1
            """,
            codes + [trade_date, sample_at],
        )
        return {row["code"]: row for row in rows}

    def _score_snapshot(
        self,
        snapshot: Dict[str, Any],
        history: List[Dict[str, Any]],
        previous: Optional[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        platform_days = config["platform_lookback_days"]
        if len(history) < platform_days:
            return None
        platform = history[-platform_days:]
        platform_high = _max_number(platform, "high")
        platform_low = _min_number(platform, "low")
        latest = safe_float(snapshot.get("latest_price"))
        if platform_high is None or platform_low is None or platform_low <= 0 or latest is None:
            return None
        platform_range = (platform_high - platform_low) / platform_low
        if platform_range > config["platform_max_range"]:
            return None

        distance_to_upper = (platform_high - latest) / platform_high
        breakout_clearance = (latest - platform_high) / platform_high
        near_upper = 0 <= distance_to_upper <= config["near_upper_distance"]
        breakout = config["breakout_min_clearance"] <= breakout_clearance <= config["breakout_max_clearance"]
        overheated = breakout_clearance > config["breakout_max_clearance"]
        if not near_upper and not breakout:
            return None
        pct_chg = safe_float(snapshot.get("pct_chg"))
        if pct_chg is not None and pct_chg > config["max_pct_chg"]:
            return None
        amount = safe_float(snapshot.get("amount"))
        if config["min_amount"] and (amount is None or amount < config["min_amount"]):
            return None

        platform_avg_amount = _avg_number(platform, "amount")
        amount_ratio = amount / platform_avg_amount if amount and platform_avg_amount and platform_avg_amount > 0 else None
        if config["min_intraday_amount_ratio"] and (
            amount_ratio is None or amount_ratio < config["min_intraday_amount_ratio"]
        ):
            return None
        ma_bullish = _ma_bullish(history)
        macd_dif, macd_dea = _macd_values([safe_float(row.get("close")) for row in history])
        macd_strong = macd_dif is not None and macd_dea is not None and macd_dif >= macd_dea
        if config["require_ma_bullish"] and not ma_bullish:
            return None
        if config["require_macd_strong"] and not macd_strong:
            return None

        volume = safe_float(snapshot.get("volume"))
        previous_price = safe_float((previous or {}).get("latest_price"))
        previous_amount = safe_float((previous or {}).get("amount"))
        previous_volume = safe_float((previous or {}).get("volume"))
        amount_delta = amount - previous_amount if amount is not None and previous_amount is not None else None
        volume_delta = volume - previous_volume if volume is not None and previous_volume is not None else None
        price_change = (latest - previous_price) / previous_price if latest and previous_price and previous_price > 0 else None

        reasons = []
        status = "接近平台"
        if breakout:
            status = "刚突破"
            reasons.append(f"突破上沿 {breakout_clearance * 100:.2f}%")
        elif near_upper:
            reasons.append(f"距上沿 {distance_to_upper * 100:.2f}%")
        if amount_ratio is not None:
            reasons.append(f"盘中额/平台均额 {amount_ratio:.2f}x")
        if amount_delta is not None:
            reasons.append(f"本段成交额 {amount_delta / 10000:.0f}万")
        if overheated:
            status = "突破过热"
        score = _radar_score(
            platform_range=platform_range,
            max_range=config["platform_max_range"],
            distance_to_upper=distance_to_upper,
            breakout_clearance=breakout_clearance,
            amount_ratio=amount_ratio,
            price_change=price_change,
            ma_bullish=ma_bullish,
            macd_strong=macd_strong,
        )
        sample_at = snapshot["sample_at"]
        return {
            "sample_at": sample_at,
            "trade_date": snapshot.get("trade_date"),
            "rank": 0,
            "code": snapshot["code"],
            "name": snapshot.get("name") or snapshot["code"],
            "status": status,
            "radar_score": round(score, 2),
            "latest_price": latest,
            "pct_chg": pct_chg,
            "amount": amount,
            "volume": volume,
            "distance_to_upper": round(distance_to_upper, 6),
            "breakout_clearance": round(breakout_clearance, 6),
            "amount_delta": _round_optional(amount_delta, 2),
            "volume_delta": _round_optional(volume_delta, 2),
            "amount_ratio": _round_optional(amount_ratio, 6),
            "price_change": _round_optional(price_change, 6),
            "source": snapshot.get("source"),
            "reasons_json": json.dumps(reasons, ensure_ascii=False),
            "metrics_json": json.dumps(
                {
                    "platform_upper": round(platform_high, 6),
                    "platform_lower": round(platform_low, 6),
                    "platform_range": round(platform_range, 6),
                    "amount_delta": _round_optional(amount_delta, 2),
                    "volume_delta": _round_optional(volume_delta, 2),
                    "price_change": _round_optional(price_change, 6),
                    "ma_bullish": ma_bullish,
                    "macd_dif": _round_optional(macd_dif, 6),
                    "macd_dea": _round_optional(macd_dea, 6),
                },
                ensure_ascii=False,
            ),
            "created_at": datetime.utcnow(),
        }

    def _sample_count(self, sample_at: Any) -> int:
        if not sample_at:
            return 0
        return int(self.db.scalar("SELECT COUNT(*) FROM intraday_snapshots WHERE sample_at = ?", [_sample_text(sample_at)]) or 0)


def normalize_intraday_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = {**DEFAULT_INTRADAY_RADAR_CONFIG, **(config or {})}
    merged["enabled"] = bool(merged.get("enabled", True))
    merged["platform_lookback_days"] = max(10, min(80, int(merged.get("platform_lookback_days") or 20)))
    for key in [
        "platform_max_range",
        "near_upper_distance",
        "breakout_min_clearance",
        "breakout_max_clearance",
        "max_pct_chg",
        "min_amount",
        "min_intraday_amount_ratio",
    ]:
        value = safe_float(merged.get(key))
        merged[key] = 0 if value is None else value
    merged["candidate_limit"] = max(1, min(500, int(merged.get("candidate_limit") or 80)))
    merged["require_ma_bullish"] = bool(merged.get("require_ma_bullish"))
    merged["require_macd_strong"] = bool(merged.get("require_macd_strong"))
    merged["include_bj"] = bool(merged.get("include_bj"))
    merged["exclude_star_board"] = bool(merged.get("exclude_star_board"))
    return merged


def _radar_score(
    platform_range: float,
    max_range: float,
    distance_to_upper: float,
    breakout_clearance: float,
    amount_ratio: Optional[float],
    price_change: Optional[float],
    ma_bullish: bool,
    macd_strong: bool,
) -> float:
    score = 45.0
    if max_range > 0:
        score += max(0.0, 1 - platform_range / max_range) * 18
    if breakout_clearance >= 0:
        score += max(0.0, 1 - min(0.08, breakout_clearance) / 0.08) * 22
    else:
        score += max(0.0, 1 - abs(distance_to_upper) / 0.03) * 14
    if amount_ratio is not None:
        score += min(18.0, amount_ratio * 12)
    if price_change is not None and price_change > 0:
        score += min(8.0, price_change * 200)
    if ma_bullish:
        score += 5
    if macd_strong:
        score += 5
    return score


def _date_value(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _sample_value(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace(" ", "T"))


def _sample_text(value: Any) -> str:
    sample = _sample_value(value)
    if sample is None:
        return str(value)
    return sample.isoformat(timespec="seconds")


def _max_number(rows: List[Dict[str, Any]], key: str) -> Optional[float]:
    values = [safe_float(row.get(key)) for row in rows]
    clean = [value for value in values if value is not None]
    return max(clean) if clean else None


def _min_number(rows: List[Dict[str, Any]], key: str) -> Optional[float]:
    values = [safe_float(row.get(key)) for row in rows]
    clean = [value for value in values if value is not None]
    return min(clean) if clean else None


def _avg_number(rows: List[Dict[str, Any]], key: str) -> Optional[float]:
    values = [safe_float(row.get(key)) for row in rows]
    clean = [value for value in values if value is not None]
    return sum(clean) / len(clean) if clean else None


def _ma_bullish(history: List[Dict[str, Any]]) -> bool:
    closes = [safe_float(row.get("close")) for row in history]
    clean = [value for value in closes if value is not None]
    if len(clean) < 20:
        return False
    ma5 = sum(clean[-5:]) / 5
    ma10 = sum(clean[-10:]) / 10
    ma20 = sum(clean[-20:]) / 20
    return ma5 >= ma10 >= ma20


def _macd_values(values: List[Optional[float]]) -> tuple[Optional[float], Optional[float]]:
    clean = [value for value in values if value is not None]
    if len(clean) < 35:
        return None, None
    series = pd.Series(clean, dtype="float64")
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    return safe_float(dif.iloc[-1]), safe_float(dea.iloc[-1])


def _round_optional(value: Optional[float], digits: int) -> Optional[float]:
    if value is None or not math.isfinite(value):
        return value
    return round(value, digits)
