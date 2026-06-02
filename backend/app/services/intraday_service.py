from __future__ import annotations

import json
import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from backend.app.db import Database
from backend.app.services.market_utils import safe_float, to_sina_chart_symbol

RADAR_MODE_STRICT = "strict"
RADAR_MODE_SCORE = "score"
RADAR_MODES = (RADAR_MODE_STRICT, RADAR_MODE_SCORE)

DEFAULT_INTRADAY_RADAR_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "platform_lookback_days": 20,
    "platform_max_range": 0.12,
    "near_upper_distance": 0.03,
    "breakout_min_clearance": 0.0,
    "breakout_max_clearance": 0.08,
    "min_pct_chg": 0.0,
    "max_pct_chg": 6.0,
    "min_amount": 50_000_000,
    "min_intraday_amount_ratio": 1.2,
    "platform_min_bullish_ratio": 0.5,
    "platform_bull_amount_advantage": 1.1,
    "first_breakout_lookback_days": 5,
    "first_breakout_max_clearance": 0.02,
    "near_upper_recent_days": 3,
    "near_upper_recent_distance": 0.03,
    "max_recent_gain_5d": 0.10,
    "candidate_limit": 80,
    "require_ma_bullish": False,
    "require_macd_strong": False,
    "include_bj": False,
    "exclude_star_board": False,
}

INTRADAY_AMOUNT_PROGRESS = [
    (9 * 60 + 35, 0.08),
    (10 * 60, 0.20),
    (10 * 60 + 30, 0.35),
    (11 * 60, 0.48),
    (11 * 60 + 25, 0.56),
    (13 * 60, 0.62),
    (13 * 60 + 30, 0.72),
    (14 * 60, 0.82),
    (14 * 60 + 30, 0.92),
    (14 * 60 + 55, 1.00),
]


class IntradayRadarService:
    def __init__(self, db: Database):
        self.db = db

    def get_config(self) -> Dict[str, Any]:
        row = self.db.query("SELECT config_json FROM intraday_radar_config WHERE id = 'default'")
        if not row:
            return normalize_intraday_config(DEFAULT_INTRADAY_RADAR_CONFIG)
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
            if not _trusted_intraday_snapshot(item):
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
                    "source": item.get("source") or "Tushare 实时日线",
                    "created_at": datetime.utcnow(),
                }
            )
        if not rows:
            return 0
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
        target_sample_time = _sample_value(target_sample)
        target_sample_text = _sample_text(target_sample_time)
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
        trade_date = _date_value(snapshots[0].get("trade_date")) or target_sample_time.date()
        history = self._history_for_snapshot([row["code"] for row in snapshots], trade_date)
        previous = self._previous_snapshots([row["code"] for row in snapshots], target_sample_time, trade_date)

        strict_rows = []
        score_rows = []
        for snapshot in snapshots:
            if snapshot.get("is_st") or snapshot.get("suspended"):
                continue
            strict_candidate = self._score_snapshot(
                snapshot,
                history.get(snapshot["code"], []),
                previous.get(snapshot["code"]),
                radar_config,
                RADAR_MODE_STRICT,
            )
            score_candidate = self._score_snapshot(
                snapshot,
                history.get(snapshot["code"], []),
                previous.get(snapshot["code"]),
                radar_config,
                RADAR_MODE_SCORE,
            )
            if strict_candidate:
                strict_rows.append(strict_candidate)
            if score_candidate:
                score_rows.append(score_candidate)
        strict_rows.sort(key=lambda row: row["radar_score"], reverse=True)
        score_rows.sort(key=lambda row: row["radar_score"], reverse=True)
        strict_limited = strict_rows[: radar_config["candidate_limit"]]
        score_limited = score_rows[: radar_config["candidate_limit"]]
        for index, row in enumerate(strict_limited, start=1):
            row["rank"] = index
        for index, row in enumerate(score_limited, start=1):
            row["rank"] = index
        self.db.execute(
            "DELETE FROM intraday_radar_candidates WHERE sample_at = ?",
            [target_sample_text],
            write=True,
        )
        self.db.execute(
            "DELETE FROM intraday_radar_rankings WHERE sample_at = ?",
            [target_sample_text],
            write=True,
        )
        legacy_strict_rows = [{key: value for key, value in row.items() if key != "radar_mode"} for row in strict_limited]
        self.db.upsert("intraday_radar_candidates", legacy_strict_rows, ["sample_at", "code"])
        self.db.upsert(
            "intraday_radar_rankings",
            strict_limited + score_limited,
            ["sample_at", "radar_mode", "code"],
        )
        return len(strict_limited)

    def latest(self, limit: int = 100) -> Dict[str, Any]:
        config = self.get_config()
        sample_at = self.db.scalar("SELECT MAX(sample_at) FROM intraday_snapshots")
        if not sample_at:
            return {
                "config": config,
                "sample_at": None,
                "sample_count": 0,
                "summary": {
                    "candidate_count": 0,
                    "strict_count": 0,
                    "score_count": 0,
                    "zero_reason": "盘中雷达尚未生成。",
                },
                "rows": [],
                "strict_rows": [],
                "score_rows": [],
            }
        strict_rows = self._ranking_rows(sample_at, RADAR_MODE_STRICT, limit)
        score_rows = self._ranking_rows(sample_at, RADAR_MODE_SCORE, limit)
        strict_count = self._ranking_count(sample_at, RADAR_MODE_STRICT)
        score_count = self._ranking_count(sample_at, RADAR_MODE_SCORE)
        if strict_count == 0 and score_count == 0:
            legacy_count = self._legacy_candidate_count(sample_at)
            if legacy_count:
                strict_rows = self._legacy_candidate_rows(sample_at, limit)
                strict_count = legacy_count
        return {
            "config": config,
            "sample_at": sample_at,
            "sample_count": self._sample_count(sample_at),
            "summary": {
                "candidate_count": strict_count,
                "strict_count": strict_count,
                "score_count": score_count,
                **(
                    {"zero_reason": "最新采样没有符合盘中雷达条件的候选。"}
                    if strict_count == 0 and score_count == 0
                    else {}
                ),
            },
            "rows": strict_rows,
            "strict_rows": strict_rows,
            "score_rows": score_rows,
        }

    def boards(self, sample_at: Optional[datetime | str] = None, limit: int = 80) -> Dict[str, Any]:
        target_sample = _sample_value(sample_at) or self.db.scalar("SELECT MAX(sample_at) FROM intraday_snapshots")
        if not target_sample:
            return {"sample_at": None, "sample_count": 0, "anomaly": [], "pullback": [], "risk": [], "theme_pulse": []}
        target_sample_time = _sample_value(target_sample)
        target_sample_text = _sample_text(target_sample_time)
        snapshots = self.db.query(
            """
            SELECT s.*, b.is_st, b.suspended
            FROM intraday_snapshots s
            LEFT JOIN stock_basic b ON b.code = s.code
            WHERE s.sample_at = ?
              AND s.latest_price IS NOT NULL
              AND (b.suspended IS DISTINCT FROM TRUE OR b.suspended IS NULL)
              AND (b.is_st IS DISTINCT FROM TRUE OR b.is_st IS NULL)
            """,
            [target_sample_text],
        )
        if not snapshots:
            return {"sample_at": target_sample, "sample_count": 0, "anomaly": [], "pullback": [], "risk": [], "theme_pulse": self._theme_pulse()}
        trade_date = _date_value(snapshots[0].get("trade_date")) or target_sample_time.date()
        codes = [row["code"] for row in snapshots]
        previous = self._previous_snapshots(codes, target_sample_time, trade_date)
        history = self._history_for_snapshot(codes, trade_date)
        theme_sync = self._theme_sync_for_codes(codes, trade_date)
        pct_values = sorted([safe_float(row.get("pct_chg")) for row in snapshots if safe_float(row.get("pct_chg")) is not None])
        amount_speed_values: List[float] = []
        scored = []
        for row in snapshots:
            amount = safe_float(row.get("amount")) or 0
            hist_amount = _avg_number(history.get(row["code"], [])[-20:], "amount")
            progress = max(_intraday_time_progress(row.get("sample_at")), 0.08)
            amount_speed = amount / (hist_amount * progress) if hist_amount and hist_amount > 0 else None
            if amount_speed is not None:
                amount_speed_values.append(amount_speed)
            prev = previous.get(row["code"]) or {}
            latest = safe_float(row.get("latest_price"))
            prev_price = safe_float(prev.get("latest_price"))
            prev_amount = safe_float(prev.get("amount"))
            high = safe_float(row.get("high"))
            low = safe_float(row.get("low"))
            amount_delta = amount - prev_amount if prev_amount is not None else None
            price_delta = latest / prev_price - 1 if latest and prev_price and prev_price > 0 else None
            drawdown = latest / high - 1 if latest and high and high > 0 else None
            open_strength = latest / low - 1 if latest and low and low > 0 else None
            pct_chg = safe_float(row.get("pct_chg"))
            pct_rank = _percentile_rank(pct_values, pct_chg)
            trend_gain = _recent_gain(history.get(row["code"], []), 20)
            risk_pullback = abs(drawdown or 0) * 100 + max(0, (safe_float(row.get("high")) or 0) - (latest or 0))
            theme = theme_sync.get(row["code"]) or {}
            metrics = {
                "intraday_amount_speed": _round_optional(amount_speed, 4),
                "amount_delta": _round_optional(amount_delta, 2),
                "price_delta": _round_optional(price_delta, 6),
                "near_day_high": _round_optional(drawdown, 6),
                "intraday_drawdown": _round_optional(drawdown, 6),
                "open_strength": _round_optional(open_strength, 6),
                "market_rank_pct_chg": _round_optional(pct_rank, 4),
                "theme_sync_score": _round_optional((safe_float(theme.get("heat_score")) or 0) / 100, 4) if theme else None,
                "strong_theme_name": theme.get("sector_name"),
                "strong_theme_heat": _round_optional(theme.get("heat_score"), 2),
                "risk_pullback_score": _round_optional(risk_pullback, 4),
                "trend_gain_20d": _round_optional(trend_gain, 6),
            }
            scored.append({**row, "metrics": metrics, "amount_speed": amount_speed, "amount_delta_value": amount_delta, "pct_rank": pct_rank})
        speed_values = sorted(amount_speed_values)
        anomaly: List[Dict[str, Any]] = []
        pullback: List[Dict[str, Any]] = []
        risk: List[Dict[str, Any]] = []
        for row in scored:
            metrics = row["metrics"]
            amount_speed = row.get("amount_speed")
            speed_rank = _percentile_rank(speed_values, amount_speed)
            pct_chg = safe_float(row.get("pct_chg")) or 0
            amount_delta = safe_float(row.get("amount_delta_value")) or 0
            drawdown = safe_float(metrics.get("intraday_drawdown")) or 0
            trend_gain = safe_float(metrics.get("trend_gain_20d")) or 0
            latest = safe_float(row.get("latest_price"))
            high = safe_float(row.get("high"))
            anomaly_score = (speed_rank or 0) * 45 + (row.get("pct_rank") or 0) * 35 + (20 if drawdown > -0.02 else 0)
            pullback_score = max(0, trend_gain * 260) + (25 if 0 <= pct_chg <= 2.5 else 0) + (20 if -0.06 <= drawdown <= -0.005 else 0)
            risk_score = max(0, -drawdown * 450) + (25 if amount_delta > 20_000_000 and pct_chg < 3 else 0) + (25 if high and latest and high > latest * 1.05 else 0)
            if amount_speed and amount_speed >= 1.5 and anomaly_score > 50:
                anomaly.append(self._board_candidate(row, "异动", anomaly_score, ["成交额速度显著放大", "涨幅排名靠前"], metrics))
            if pullback_score >= 25:
                pullback.append(self._board_candidate(row, "低吸", pullback_score, ["趋势保持", "日内涨幅不过热"], metrics))
            if risk_score >= 25:
                risk.append(self._board_candidate(row, "风险", risk_score, ["冲高回落或放量滞涨"], metrics))
        anomaly.sort(key=lambda item: item["radar_score"], reverse=True)
        pullback.sort(key=lambda item: item["radar_score"], reverse=True)
        risk.sort(key=lambda item: item["radar_score"], reverse=True)
        for rows in [anomaly, pullback, risk]:
            for index, item in enumerate(rows[:limit], start=1):
                item["rank"] = index
        return {
            "sample_at": target_sample,
            "sample_count": self._sample_count(target_sample),
            "anomaly": anomaly[:limit],
            "pullback": pullback[:limit],
            "risk": risk[:limit],
            "theme_pulse": self._theme_pulse(),
        }

    def _board_candidate(
        self,
        row: Dict[str, Any],
        status: str,
        score: float,
        reasons: List[str],
        metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        code = str(row.get("code"))
        return {
            "sample_at": row.get("sample_at"),
            "trade_date": row.get("trade_date"),
            "rank": 0,
            "radar_mode": status,
            "code": code,
            "name": row.get("name") or code,
            "status": status,
            "radar_score": round(score, 2),
            "latest_price": safe_float(row.get("latest_price")),
            "pct_chg": safe_float(row.get("pct_chg")),
            "amount": safe_float(row.get("amount")),
            "volume": safe_float(row.get("volume")),
            "source": row.get("source"),
            "reasons": reasons,
            "metrics": metrics,
            "intraday_amount_speed": metrics.get("intraday_amount_speed"),
            "amount_delta": metrics.get("amount_delta"),
            "theme_sync_score": metrics.get("theme_sync_score"),
            "strong_theme_name": metrics.get("strong_theme_name"),
            "strong_theme_heat": metrics.get("strong_theme_heat"),
            "intraday_drawdown": metrics.get("intraday_drawdown"),
            "open_strength": metrics.get("open_strength"),
            "risk_pullback_score": metrics.get("risk_pullback_score"),
            "chart_url": f"https://finance.sina.com.cn/realstock/company/{to_sina_chart_symbol(code)}/nc.shtml",
        }

    def _theme_sync_for_codes(self, codes: List[str], trade_date: date) -> Dict[str, Dict[str, Any]]:
        clean_codes = sorted({str(code) for code in codes if code})
        if not clean_codes:
            return {}
        sector_date = self.db.scalar(
            """
            SELECT MAX(trade_date)
            FROM market_sector_daily
            WHERE trade_date <= ?
            """,
            [trade_date],
        )
        if not sector_date:
            return {}
        placeholders = ",".join(["?"] * len(clean_codes))
        rows = self.db.query(
            f"""
            SELECT m.code,
                   d.sector_code,
                   d.sector_name,
                   d.heat_score
            FROM tushare_ths_member m
            JOIN market_sector_daily d
              ON d.sector_code = m.con_code
            WHERE m.code IN ({placeholders})
              AND d.trade_date = ?
              AND d.heat_score IS NOT NULL
            ORDER BY m.code, d.heat_score DESC
            """,
            [*clean_codes, sector_date],
        )
        output: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            output.setdefault(str(row["code"]), row)
        return output

    def _theme_pulse(self) -> List[Dict[str, Any]]:
        rows = self.db.query(
            """
            SELECT sector_code AS code,
                   sector_name AS name,
                   sector_type AS type,
                   pct_chg,
                   net_amount,
                   company_count,
                   limit_up_count,
                   strong_count,
                   leader_name,
                   heat_score
            FROM market_sector_daily
            WHERE trade_date = (SELECT MAX(trade_date) FROM market_sector_daily)
            ORDER BY heat_score DESC NULLS LAST
            LIMIT 12
            """
        )
        return rows

    def timeline(self, code: str, trade_date: Optional[str | date] = None, limit: int = 50) -> Dict[str, Any]:
        target_date = _date_value(trade_date) or self.db.scalar(
            """
            SELECT MAX(trade_date)
            FROM intraday_snapshots
            WHERE code = ?
            """,
            [code],
        )
        if not target_date:
            return {"code": code, "name": code, "trade_date": None, "rows": []}
        snapshots = self.db.query(
            """
            SELECT *
            FROM intraday_snapshots
            WHERE code = ?
              AND trade_date = ?
            ORDER BY sample_at
            LIMIT ?
            """,
            [code, target_date, max(1, min(limit, 200))],
        )
        rankings = self.db.query(
            """
            SELECT *
            FROM intraday_radar_rankings
            WHERE code = ?
              AND trade_date = ?
            ORDER BY sample_at, radar_mode
            """,
            [code, target_date],
        )
        decoded_rankings = _decode_candidate_rows(rankings)
        ranking_by_sample: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for row in decoded_rankings:
            ranking_by_sample.setdefault(_sample_text(row.get("sample_at")), {})[row["radar_mode"]] = row
        history = self._history_for_snapshot([code], _date_value(target_date) or date.today()).get(code, [])
        platform_avg_amount = _avg_number(history[-20:], "amount")
        rows: List[Dict[str, Any]] = []
        previous_snapshot: Optional[Dict[str, Any]] = None
        for snapshot in snapshots:
            sample_key = _sample_text(snapshot.get("sample_at"))
            strict = ranking_by_sample.get(sample_key, {}).get(RADAR_MODE_STRICT)
            score = ranking_by_sample.get(sample_key, {}).get(RADAR_MODE_SCORE)
            chosen = strict or score or {}
            metrics = chosen.get("metrics") or {}
            amount = safe_float(snapshot.get("amount"))
            volume = safe_float(snapshot.get("volume"))
            previous_amount = safe_float((previous_snapshot or {}).get("amount"))
            previous_volume = safe_float((previous_snapshot or {}).get("volume"))
            computed_amount_delta = amount - previous_amount if amount is not None and previous_amount is not None else None
            computed_volume_delta = volume - previous_volume if volume is not None and previous_volume is not None else None
            expected_amount = (
                platform_avg_amount * _intraday_time_progress(snapshot.get("sample_at"))
                if platform_avg_amount and platform_avg_amount > 0
                else None
            )
            computed_amount_ratio = amount / expected_amount if amount and expected_amount and expected_amount > 0 else None
            chosen_amount_ratio = safe_float(chosen.get("amount_ratio"))
            rows.append(
                {
                    "sample_at": snapshot.get("sample_at"),
                    "trade_date": snapshot.get("trade_date"),
                    "latest_price": safe_float(snapshot.get("latest_price")),
                    "pct_chg": safe_float(snapshot.get("pct_chg")),
                    "amount": amount,
                    "volume": volume,
                    "strict_status": strict.get("status") if strict else None,
                    "strict_score": strict.get("radar_score") if strict else None,
                    "score_status": score.get("status") if score else None,
                    "score_score": score.get("radar_score") if score else None,
                    "distance_to_upper": chosen.get("distance_to_upper"),
                    "breakout_clearance": chosen.get("breakout_clearance"),
                    "amount_ratio": _round_optional(chosen_amount_ratio if chosen_amount_ratio is not None else computed_amount_ratio, 6),
                    "amount_ratio_status": "computed" if chosen_amount_ratio is not None or computed_amount_ratio is not None else "missing_history_amount",
                    "amount_delta": _round_optional(computed_amount_delta if computed_amount_delta is not None else chosen.get("amount_delta"), 2),
                    "amount_delta_status": "computed" if computed_amount_delta is not None or chosen.get("amount_delta") is not None else "insufficient_samples",
                    "volume_delta": _round_optional(computed_volume_delta if computed_volume_delta is not None else chosen.get("volume_delta"), 2),
                    "platform_upper": metrics.get("platform_upper"),
                    "platform_range": metrics.get("platform_range"),
                    "reasons": chosen.get("reasons") or [],
                }
            )
            previous_snapshot = snapshot
        name = snapshots[-1].get("name") if snapshots else code
        return {"code": code, "name": name or code, "trade_date": target_date, "rows": rows}

    def _ranking_rows(self, sample_at: Any, radar_mode: str, limit: int) -> List[Dict[str, Any]]:
        rows = self.db.query(
            """
            SELECT *
            FROM intraday_radar_rankings
            WHERE sample_at = ?
              AND radar_mode = ?
            ORDER BY rank
            LIMIT ?
            """,
            [_sample_text(sample_at), radar_mode, max(1, min(limit, 500))],
        )
        return _decode_candidate_rows(rows)

    def _ranking_count(self, sample_at: Any, radar_mode: str) -> int:
        return int(
            self.db.scalar(
                """
                SELECT COUNT(*)
                FROM intraday_radar_rankings
                WHERE sample_at = ?
                  AND radar_mode = ?
                """,
                [_sample_text(sample_at), radar_mode],
            )
            or 0
        )

    def _legacy_candidate_rows(self, sample_at: Any, limit: int) -> List[Dict[str, Any]]:
        rows = self.db.query(
            """
            SELECT *, 'strict' AS radar_mode
            FROM intraday_radar_candidates
            WHERE sample_at = ?
            ORDER BY rank
            LIMIT ?
            """,
            [_sample_text(sample_at), max(1, min(limit, 500))],
        )
        return _decode_candidate_rows(rows)

    def _legacy_candidate_count(self, sample_at: Any) -> int:
        return int(
            self.db.scalar(
                "SELECT COUNT(*) FROM intraday_radar_candidates WHERE sample_at = ?",
                [_sample_text(sample_at)],
            )
            or 0
        )

    def _sample_count(self, sample_at: Any) -> int:
        if not sample_at:
            return 0
        return int(self.db.scalar("SELECT COUNT(*) FROM intraday_snapshots WHERE sample_at = ?", [_sample_text(sample_at)]) or 0)

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
        sample_at: datetime,
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
              AND sample_at < CAST(? AS TIMESTAMP)
            QUALIFY ROW_NUMBER() OVER (PARTITION BY code ORDER BY sample_at DESC) = 1
            """,
            codes + [trade_date, _sample_text(sample_at)],
        )
        return {row["code"]: row for row in rows}

    def _score_snapshot(
        self,
        snapshot: Dict[str, Any],
        history: List[Dict[str, Any]],
        previous: Optional[Dict[str, Any]],
        config: Dict[str, Any],
        radar_mode: str,
    ) -> Optional[Dict[str, Any]]:
        strict = radar_mode == RADAR_MODE_STRICT
        platform_days = config["platform_lookback_days"]
        if len(history) < platform_days:
            return None
        platform, recent_prior = _split_platform_history(
            history,
            platform_days,
            config["first_breakout_lookback_days"],
        )
        platform_high = _max_number(platform, "high")
        platform_low = _min_number(platform, "low")
        latest = safe_float(snapshot.get("latest_price"))
        if platform_high is None or platform_low is None or platform_low <= 0 or latest is None:
            return None
        platform_range = (platform_high - platform_low) / platform_low
        range_limit = config["platform_max_range"]
        if strict and range_limit and platform_range > range_limit:
            return None
        if not strict and range_limit and platform_range > max(range_limit * 1.8, range_limit + 0.08):
            return None

        distance_to_upper = (platform_high - latest) / platform_high
        breakout_clearance = (latest - platform_high) / platform_high
        near_upper = 0 <= distance_to_upper <= config["near_upper_distance"]
        breakout = config["breakout_min_clearance"] <= breakout_clearance <= config["breakout_max_clearance"]
        overheated = breakout_clearance > config["breakout_max_clearance"]
        near_enough_for_score = (
            distance_to_upper >= 0
            and distance_to_upper <= max(config["near_upper_distance"] * 2.5, config["near_upper_distance"] + 0.03)
        )
        breakout_enough_for_score = (
            breakout_clearance >= config["breakout_min_clearance"] * 0.5
            and breakout_clearance <= max(config["breakout_max_clearance"] * 1.6, config["breakout_max_clearance"] + 0.04)
        )
        if strict and not near_upper and not breakout:
            return None
        if not strict and not near_enough_for_score and not breakout_enough_for_score:
            return None
        pct_chg = safe_float(snapshot.get("pct_chg"))
        if strict and pct_chg is not None and pct_chg < config["min_pct_chg"]:
            return None
        if strict and pct_chg is not None and config["max_pct_chg"] and pct_chg > config["max_pct_chg"]:
            return None
        if (
            not strict
            and pct_chg is not None
            and config["max_pct_chg"]
            and pct_chg > max(config["max_pct_chg"] + 4.0, config["max_pct_chg"] * 1.5)
        ):
            return None
        amount = safe_float(snapshot.get("amount"))
        if strict and config["min_amount"] and (amount is None or amount < config["min_amount"]):
            return None
        if not strict and config["min_amount"] and (amount is None or amount < config["min_amount"] * 0.35):
            return None

        platform_avg_amount = _avg_number(platform, "amount")
        intraday_time_progress = _intraday_time_progress(snapshot.get("sample_at"))
        expected_amount = (
            platform_avg_amount * intraday_time_progress
            if platform_avg_amount and platform_avg_amount > 0 and intraday_time_progress > 0
            else None
        )
        amount_ratio = amount / expected_amount if amount and expected_amount and expected_amount > 0 else None
        if strict and config["min_intraday_amount_ratio"] and (
            amount_ratio is None or amount_ratio < config["min_intraday_amount_ratio"]
        ):
            return None
        if not strict and config["min_intraday_amount_ratio"] and (
            amount_ratio is None or amount_ratio < config["min_intraday_amount_ratio"] * 0.35
        ):
            return None
        bullish_ratio = _bullish_ratio(platform)
        bull_amount_advantage = _bull_amount_advantage(platform)
        recent_gain_5d = _recent_gain(history, 5)
        first_breakout_clearance = _prior_breakout_clearance(recent_prior, platform_high)
        if (
            strict
            and first_breakout_clearance is not None
            and config["first_breakout_max_clearance"] >= 0
            and first_breakout_clearance > config["first_breakout_max_clearance"]
        ):
            return None
        recent_near_upper_distance = _recent_near_upper_distance(
            history,
            platform_high,
            config["near_upper_recent_days"],
        )
        if (
            strict
            and recent_near_upper_distance is not None
            and config["near_upper_recent_distance"] > 0
            and recent_near_upper_distance > config["near_upper_recent_distance"]
        ):
            return None
        if strict and bullish_ratio is not None and bullish_ratio < config["platform_min_bullish_ratio"]:
            return None
        if strict and bull_amount_advantage is not None and bull_amount_advantage < config["platform_bull_amount_advantage"]:
            return None
        if strict and recent_gain_5d is not None and config["max_recent_gain_5d"] and recent_gain_5d > config["max_recent_gain_5d"]:
            return None
        if (
            not strict
            and recent_gain_5d is not None
            and config["max_recent_gain_5d"]
            and recent_gain_5d > max(config["max_recent_gain_5d"] * 2.0, config["max_recent_gain_5d"] + 0.10)
        ):
            return None
        ma_bullish = _ma_bullish(history)
        macd_dif, macd_dea = _macd_values([safe_float(row.get("close")) for row in history])
        macd_strong = macd_dif is not None and macd_dea is not None and macd_dif >= macd_dea
        if strict and config["require_ma_bullish"] and not ma_bullish:
            return None
        if strict and config["require_macd_strong"] and not macd_strong:
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
        if radar_mode == RADAR_MODE_SCORE:
            status = "综合观察"
        if breakout:
            status = "刚突破"
            reasons.append(f"突破上沿 {breakout_clearance * 100:.2f}%")
        elif near_upper:
            reasons.append(f"距上沿 {distance_to_upper * 100:.2f}%")
        elif radar_mode == RADAR_MODE_SCORE and near_enough_for_score:
            reasons.append(f"距上沿 {distance_to_upper * 100:.2f}%")
        elif radar_mode == RADAR_MODE_SCORE and breakout_clearance > 0:
            reasons.append(f"突破偏高 {breakout_clearance * 100:.2f}%")
        if amount_ratio is not None:
            reasons.append(f"时段量能 {amount_ratio:.2f}x")
        if bullish_ratio is not None:
            reasons.append(f"阳线占比 {bullish_ratio * 100:.0f}%")
        if bull_amount_advantage is not None:
            reasons.append(f"阳线均额 {bull_amount_advantage:.2f}x")
        if first_breakout_clearance is not None and first_breakout_clearance > config["first_breakout_max_clearance"]:
            reasons.append(f"近{config['first_breakout_lookback_days']}日已突破 {first_breakout_clearance * 100:.2f}%")
        if recent_near_upper_distance is not None:
            reasons.append(f"近{config['near_upper_recent_days']}日贴沿 {recent_near_upper_distance * 100:.2f}%")
        if amount_delta is not None:
            reasons.append(f"本段成交额 {amount_delta / 10000:.0f}万")
        if overheated and strict:
            status = "突破过热"
        score = _radar_score(
            platform_range=platform_range,
            max_range=config["platform_max_range"],
            distance_to_upper=distance_to_upper,
            breakout_clearance=breakout_clearance,
            amount_ratio=amount_ratio,
            price_change=price_change,
            bullish_ratio=bullish_ratio,
            bull_amount_advantage=bull_amount_advantage,
            recent_gain_5d=recent_gain_5d,
            max_recent_gain_5d=config["max_recent_gain_5d"],
            first_breakout_clearance=first_breakout_clearance,
            first_breakout_max_clearance=config["first_breakout_max_clearance"],
            recent_near_upper_distance=recent_near_upper_distance,
            near_upper_recent_distance=config["near_upper_recent_distance"],
            pct_chg=pct_chg,
            min_pct_chg=config["min_pct_chg"],
            ma_bullish=ma_bullish,
            macd_strong=macd_strong,
        )
        sample_at = snapshot["sample_at"]
        return {
            "sample_at": sample_at,
            "radar_mode": radar_mode,
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
                    "platform_bullish_ratio": _round_optional(bullish_ratio, 6),
                    "platform_bull_amount_advantage": _round_optional(bull_amount_advantage, 6),
                    "recent_gain_5d": _round_optional(recent_gain_5d, 6),
                    "recent_prior_breakout_clearance": _round_optional(first_breakout_clearance, 6),
                    "recent_near_upper_distance": _round_optional(recent_near_upper_distance, 6),
                    "recent_near_upper_days": config["near_upper_recent_days"],
                    "intraday_time_progress": _round_optional(intraday_time_progress, 6),
                    "platform_avg_amount": _round_optional(platform_avg_amount, 2),
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


def normalize_intraday_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = {**DEFAULT_INTRADAY_RADAR_CONFIG, **(config or {})}
    merged["enabled"] = bool(merged.get("enabled", True))
    merged["platform_lookback_days"] = max(10, min(80, int(merged.get("platform_lookback_days") or 20)))
    merged["first_breakout_lookback_days"] = max(0, min(20, int(merged.get("first_breakout_lookback_days") or 0)))
    merged["near_upper_recent_days"] = max(0, min(20, int(merged.get("near_upper_recent_days") or 0)))
    for key in [
        "platform_max_range",
        "near_upper_distance",
        "breakout_min_clearance",
        "breakout_max_clearance",
        "min_pct_chg",
        "max_pct_chg",
        "min_amount",
        "min_intraday_amount_ratio",
        "platform_min_bullish_ratio",
        "platform_bull_amount_advantage",
        "first_breakout_max_clearance",
        "near_upper_recent_distance",
        "max_recent_gain_5d",
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
    bullish_ratio: Optional[float],
    bull_amount_advantage: Optional[float],
    recent_gain_5d: Optional[float],
    max_recent_gain_5d: float,
    first_breakout_clearance: Optional[float],
    first_breakout_max_clearance: float,
    recent_near_upper_distance: Optional[float],
    near_upper_recent_distance: float,
    pct_chg: Optional[float],
    min_pct_chg: float,
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
    if bullish_ratio is not None:
        score += min(10.0, bullish_ratio * 12)
    if bull_amount_advantage is not None:
        score += min(8.0, max(0.0, bull_amount_advantage - 1.0) * 24)
    if recent_gain_5d is not None and max_recent_gain_5d > 0:
        score -= max(0.0, recent_gain_5d - max_recent_gain_5d) * 90
    if first_breakout_clearance is not None and first_breakout_max_clearance >= 0:
        score -= max(0.0, first_breakout_clearance - first_breakout_max_clearance) * 160
    if recent_near_upper_distance is not None and near_upper_recent_distance > 0:
        score += max(0.0, 1 - max(0.0, recent_near_upper_distance) / near_upper_recent_distance) * 8
    if pct_chg is not None:
        score -= max(0.0, min_pct_chg - pct_chg) * 2
    if price_change is not None and price_change > 0:
        score += min(8.0, price_change * 200)
    if ma_bullish:
        score += 5
    if macd_strong:
        score += 5
    return score


def _decode_candidate_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for row in rows:
        row["reasons"] = json.loads(row.pop("reasons_json") or "[]")
        row["metrics"] = json.loads(row.pop("metrics_json") or "{}")
        row["chart_url"] = f"https://finance.sina.com.cn/realstock/company/{to_sina_chart_symbol(row['code'])}/nc.shtml"
    return rows


def _trusted_intraday_snapshot(item: Dict[str, Any]) -> bool:
    source = str(item.get("source") or "")
    freshness = str(item.get("freshness") or "").strip().lower()
    if freshness and freshness not in {"realtime", "real_time", "intraday"}:
        return False
    if "日线回退" in source or "daily_fallback" in source.lower():
        return False
    if _snapshot_is_st_or_suspended(item, source):
        return False

    latest = safe_float(item.get("latest_price"))
    high = safe_float(item.get("high"))
    low = safe_float(item.get("low"))
    pct_chg = safe_float(item.get("pct_chg"))
    amount = safe_float(item.get("amount"))
    volume = safe_float(item.get("volume"))
    if latest is None or latest <= 0:
        return False
    if high is not None and high <= 0:
        return False
    if low is not None and low <= 0:
        return False
    if high is not None and low is not None and high < low:
        return False
    if amount is not None and amount < 0:
        return False
    if volume is not None and volume < 0:
        return False
    if pct_chg is not None and not -40.0 <= pct_chg <= 40.0:
        return False
    return True


def _snapshot_is_st_or_suspended(item: Dict[str, Any], source: str) -> bool:
    name = str(item.get("name") or "").strip().upper()
    if name.startswith("ST") or name.startswith("*ST"):
        return True
    status = item.get("tradestatus")
    if status is None:
        status = item.get("trade_status")
    if status is None:
        status = item.get("status")
    if status is False:
        return True
    status_text = str(status or "").strip().lower()
    if status_text in {"0", "false", "停牌", "suspended", "halt", "halted", "paused"}:
        return True
    source_text = source.lower()
    return "停牌" in source or "suspended" in source_text or "halted" in source_text


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


def _intraday_time_progress(value: Any) -> float:
    sample = _sample_value(value)
    if sample is None:
        return 1.0
    minute = sample.hour * 60 + sample.minute + sample.second / 60
    first_minute, first_progress = INTRADAY_AMOUNT_PROGRESS[0]
    if minute <= first_minute:
        return first_progress
    for (start_minute, start_progress), (end_minute, end_progress) in zip(
        INTRADAY_AMOUNT_PROGRESS,
        INTRADAY_AMOUNT_PROGRESS[1:],
    ):
        if minute <= end_minute:
            span = end_minute - start_minute
            if span <= 0:
                return end_progress
            ratio = (minute - start_minute) / span
            return start_progress + (end_progress - start_progress) * ratio
    return INTRADAY_AMOUNT_PROGRESS[-1][1]


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


def _split_platform_history(
    history: List[Dict[str, Any]],
    platform_days: int,
    first_breakout_lookback_days: int,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if first_breakout_lookback_days <= 0 or len(history) < platform_days + first_breakout_lookback_days:
        return history[-platform_days:], []
    platform_end = len(history) - first_breakout_lookback_days
    return history[platform_end - platform_days : platform_end], history[platform_end:]


def _prior_breakout_clearance(rows: List[Dict[str, Any]], platform_high: float) -> Optional[float]:
    if not rows or platform_high <= 0:
        return None
    recent_close = _max_number(rows, "close")
    if recent_close is None:
        return None
    return (recent_close - platform_high) / platform_high


def _recent_near_upper_distance(
    history: List[Dict[str, Any]],
    platform_high: float,
    recent_days: int,
) -> Optional[float]:
    if recent_days <= 0 or len(history) < recent_days or platform_high <= 0:
        return None
    recent_high = _max_number(history[-recent_days:], "high")
    if recent_high is None:
        return None
    return (platform_high - recent_high) / platform_high


def _bullish_ratio(rows: List[Dict[str, Any]]) -> Optional[float]:
    valid = [
        row
        for row in rows
        if safe_float(row.get("open")) is not None and safe_float(row.get("close")) is not None
    ]
    if not valid:
        return None
    bullish = [
        row
        for row in valid
        if (safe_float(row.get("close")) or 0) > (safe_float(row.get("open")) or 0)
    ]
    return len(bullish) / len(valid)


def _bull_amount_advantage(rows: List[Dict[str, Any]]) -> Optional[float]:
    bullish_amounts = []
    bearish_amounts = []
    for row in rows:
        open_price = safe_float(row.get("open"))
        close_price = safe_float(row.get("close"))
        amount = safe_float(row.get("amount"))
        if open_price is None or close_price is None or amount is None:
            continue
        if close_price > open_price:
            bullish_amounts.append(amount)
        else:
            bearish_amounts.append(amount)
    if not bullish_amounts:
        return 0.0
    if not bearish_amounts:
        return 9.99
    bearish_avg = sum(bearish_amounts) / len(bearish_amounts)
    if bearish_avg <= 0:
        return None
    return (sum(bullish_amounts) / len(bullish_amounts)) / bearish_avg


def _recent_gain(history: List[Dict[str, Any]], window: int) -> Optional[float]:
    closes = [safe_float(row.get("close")) for row in history]
    clean = [value for value in closes if value is not None]
    if len(clean) <= window or clean[-window - 1] <= 0:
        return None
    return (clean[-1] - clean[-window - 1]) / clean[-window - 1]


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


def _percentile_rank(values: List[float], value: Optional[float]) -> Optional[float]:
    if value is None or not values:
        return None
    ordered = [item for item in values if item is not None and math.isfinite(item)]
    if not ordered:
        return None
    below_or_equal = sum(1 for item in ordered if item <= value)
    return below_or_equal / len(ordered)
