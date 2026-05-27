from __future__ import annotations

import json
import hashlib
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import duckdb

from backend.app.db import Database


FEATURE_DRIVEN_SIGNAL_MODE = "feature_driven"

DEFAULT_STRATEGY_CONFIG: Dict[str, Any] = {
    "min_price": 4.0,
    "min_amount": 80_000_000,
    "min_float_market_value": None,
    "max_float_market_value": None,
    "ma_short_window": 20,
    "ma_long_window": 60,
    "trend_filter": "ma_short_above_long",
    "analysis_mode": "strict",
    "signal_mode": FEATURE_DRIVEN_SIGNAL_MODE,
    "breakout_pullback_direction": "both",
    "breakout_lookback": 20,
    "pullback_tolerance": 0.035,
    "platform_lookback_days": 20,
    "platform_max_range": 0.12,
    "platform_max_range_mode": "must",
    "platform_range_basis": "high_low",
    "platform_breakout_require_close_above": True,
    "platform_breakout_clearance_mode": "must",
    "platform_breakout_clearance": 0.03,
    "platform_breakout_max_clearance": 0.08,
    "platform_breakout_max_clearance_mode": "score",
    "platform_breakout_first_mode": "must",
    "platform_min_bullish_ratio": 0.5,
    "platform_bullish_ratio_mode": "must",
    "platform_bullish_ratio_score": 0.6,
    "platform_bull_volume_advantage": 1.1,
    "platform_bull_volume_advantage_mode": "must",
    "platform_bull_volume_advantage_score": 1.2,
    "platform_breakout_volume_ratio": 3.0,
    "platform_breakout_volume_ratio_mode": "must",
    "platform_breakout_pct_chg_min": 5.0,
    "platform_breakout_pct_chg_mode": "must",
    "platform_breakout_bullish_mode": "must",
    "platform_body_strength_min": 1.0,
    "platform_body_strength_mode": "must",
    "platform_ma_trend_enabled": True,
    "platform_ma_bullish_mode": "score",
    "platform_ma_rising_required": True,
    "platform_ma_rising_mode": "score",
    "platform_macd_filter_mode": "score",
    "platform_setup_lookback_days": 20,
    "platform_setup_max_range": 0.1,
    "platform_setup_max_distance_to_high": 0.035,
    "platform_setup_max_recent_gain_5d": 0.1,
    "platform_setup_volume_contraction_max": 1.05,
    "platform_setup_bull_volume_advantage": 1.05,
    "platform_setup_ma_convergence_max": 0.05,
    "platform_setup_require_ma_turning": True,
    "platform_setup_macd_mode": "dif_above_dea",
    "trend_ema_fast_window": 13,
    "trend_ema_mid_window": 21,
    "trend_ema_long_window": 60,
    "trend_macd_fast": 4,
    "trend_macd_slow": 26,
    "trend_macd_signal": 6,
    "trend_stoch_window": 27,
    "trend_stoch_k_smooth": 9,
    "trend_stoch_d_smooth": 3,
    "trend_entry_signal": "any",
    "trend_require_price_above_ema_long": True,
    "trend_require_ema_long_rising": True,
    "trend_require_ema_fast_above_mid": True,
    "trend_macd_mode": "dif_above_dea",
    "trend_stoch_mode": "k_above_d",
    "trend_max_ema_mid_distance": 0.12,
    "trend_max_recent_gain_10d": 0.28,
    "trend_stoch_overheat": 85.0,
    "macd_filter_enabled": True,
    "macd_position": "dif_dea_above_zero",
    "max_amplitude": 0.12,
    "rps_window": 20,
    "min_rps20": 70.0,
    "min_rps60": None,
    "min_rps120": None,
    "min_turnover": None,
    "max_turnover": 12.0,
    "missing_turnover_policy": "allow",
    "min_pct_chg": -4.5,
    "max_pct_chg": 9.8,
    "volume_ratio_min": 1.1,
    "max_ma_distance": 0.18,
    "min_topic_count": None,
    "min_topic_heat": None,
    "min_theme_limit_count": None,
    "candidate_limit": 50,
    "sort_by": "signal_score",
    "missing_float_market_value_policy": "allow",
    "include_bj": False,
    "exclude_star_board": False,
    "analysis_engines": [],
    "strategy_rules": [],
    "strategy_interactions": [],
    "strategy_resonances": [],
    "resonance_bonus_cap": 15,
}

RULE_ACTIONS = {"filter", "score", "risk", "display"}
RULE_OPERATORS = {"gte", "lte", "gt", "lt", "between", "eq", "neq", "is_true", "recent"}
RULE_MISSING_POLICIES = {"skip", "keep", "neutral", "allow"}
ANALYSIS_ENGINES = ("platform_breakout", "platform_setup", "trend_resonance")
LEGACY_SIGNAL_MODES = {
    "breakout",
    "pullback",
    "breakout_or_pullback",
    "platform_breakout",
    "platform_setup",
    "trend_resonance",
}
LEGACY_SIGNAL_MODE_FEATURE_GROUPS = {
    "platform_breakout": "platform_breakout",
    "platform_setup": "platform_setup",
    "trend_resonance": "trend_resonance",
}


def _coerce_number(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _normalize_strategy_rules(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            continue
        indicator_id = str(raw.get("indicator_id") or "").strip()
        if not indicator_id:
            continue
        action = str(raw.get("action") or "display")
        if action not in RULE_ACTIONS:
            action = "display"
        operator = str(raw.get("operator") or "gte")
        if operator not in RULE_OPERATORS:
            operator = "gte"
        rule_id = str(raw.get("id") or f"{indicator_id}-{action}-{index + 1}").strip()
        if not rule_id or rule_id in seen:
            rule_id = f"{indicator_id}-{action}-{index + 1}"
        seen.add(rule_id)
        missing_policy = str(raw.get("missing_policy") or "neutral")
        if missing_policy not in RULE_MISSING_POLICIES:
            missing_policy = "neutral"
        value_one = raw.get("value")
        value_two = raw.get("value2")
        numeric_one = _coerce_number(value_one)
        numeric_two = _coerce_number(value_two)
        if numeric_one is not None:
            value_one = numeric_one
        if numeric_two is not None:
            value_two = numeric_two
        weight = _coerce_number(raw.get("weight"))
        normalized.append(
            {
                "id": rule_id,
                "indicator_id": indicator_id,
                "action": action,
                "operator": operator,
                "value": value_one,
                "value2": value_two,
                "window_days": int(_coerce_number(raw.get("window_days")) or 0),
                "weight": weight if weight is not None else None,
                "missing_policy": missing_policy,
                "enabled": bool(raw.get("enabled", True)),
            }
        )
    return normalized


def _normalize_rule_condition(raw: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
    indicator_id = str(raw.get("indicator_id") or "").strip()
    if not indicator_id:
        return None
    operator = str(raw.get("operator") or "gte")
    if operator not in RULE_OPERATORS:
        operator = "gte"
    missing_policy = str(raw.get("missing_policy") or "neutral")
    if missing_policy not in RULE_MISSING_POLICIES:
        missing_policy = "neutral"
    value_one = raw.get("value")
    value_two = raw.get("value2")
    numeric_one = _coerce_number(value_one)
    numeric_two = _coerce_number(value_two)
    if numeric_one is not None:
        value_one = numeric_one
    if numeric_two is not None:
        value_two = numeric_two
    return {
        "id": str(raw.get("id") or f"{indicator_id}-{index + 1}"),
        "indicator_id": indicator_id,
        "operator": operator,
        "value": value_one,
        "value2": value_two,
        "window_days": int(_coerce_number(raw.get("window_days")) or 0),
        "missing_policy": missing_policy,
    }


def _normalize_strategy_interactions(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            continue
        conditions = [
            condition
            for condition in (
                _normalize_rule_condition(condition_raw, condition_index)
                for condition_index, condition_raw in enumerate(raw.get("conditions") or [])
                if isinstance(condition_raw, dict)
            )
            if condition is not None
        ]
        if len(conditions) < 2:
            continue
        rule_id = str(raw.get("id") or f"interaction-{index + 1}").strip()
        if not rule_id or rule_id in seen:
            rule_id = f"interaction-{index + 1}"
        seen.add(rule_id)
        multiplier = _coerce_number(raw.get("multiplier"))
        if multiplier is None:
            multiplier = 1.0
        multiplier = max(0.5, min(1.6, float(multiplier)))
        normalized.append(
            {
                "id": rule_id,
                "name": str(raw.get("name") or "组合条件"),
                "conditions": conditions,
                "multiplier": round(multiplier, 2),
                "enabled": bool(raw.get("enabled", True)),
            }
        )
    return normalized


def _rule_signature(rule: Dict[str, Any]) -> tuple:
    return (
        str(rule.get("indicator_id") or ""),
        str(rule.get("operator") or ""),
        rule.get("value"),
        rule.get("value2"),
        int(_coerce_number(rule.get("window_days")) or 0),
    )


def _legacy_resonance_bonus(multiplier: Any) -> float:
    value = _coerce_number(multiplier)
    if value is None:
        return 5.0
    if value <= 1:
        return 0.0
    if value <= 1.1:
        return 5.0
    if value <= 1.2:
        return 8.0
    return 12.0


def _disabled_resonance(
    resonance_id: str,
    name: str,
    bonus: float,
    conditions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "id": resonance_id,
        "name": name,
        "rule_ids": [],
        "bonus": round(bonus, 2),
        "enabled": False,
        "source": "legacy_unmatched",
        "migration_warning": f"组合共振「{name}」无法匹配至少两个筛选/加分规则，已停用；可恢复为补充规则后重新启用。",
        "legacy_conditions": conditions or [],
    }


def _normalize_strategy_resonances(value: Any, strategy_rules: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: List[Dict[str, Any]] = []
    seen: set[str] = set()
    rules = strategy_rules or []
    eligible_rule_ids = {str(rule.get("id") or "") for rule in rules if rule.get("action") in {"filter", "score"}}
    rule_id_by_signature = {
        _rule_signature(rule): str(rule.get("id"))
        for rule in rules
        if rule.get("id") and rule.get("action") in {"filter", "score"}
    }
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            continue
        resonance_id = str(raw.get("id") or f"resonance-{index + 1}").strip()
        if not resonance_id or resonance_id in seen:
            resonance_id = f"resonance-{index + 1}"
        seen.add(resonance_id)
        resonance_name = str(raw.get("name") or "组合共振")
        bonus = _coerce_number(raw.get("bonus"))
        if bonus is None:
            bonus = _legacy_resonance_bonus(raw.get("multiplier"))
        bonus = max(0.0, min(25.0, float(bonus)))
        referenced_rule_ids = [str(item) for item in raw.get("rule_ids") or [] if str(item) in eligible_rule_ids]
        conditions: List[Dict[str, Any]] = []
        if len(referenced_rule_ids) < 2:
            conditions = [
                condition
                for condition in (
                    _normalize_rule_condition(condition_raw, condition_index)
                    for condition_index, condition_raw in enumerate(raw.get("conditions") or [])
                    if isinstance(condition_raw, dict)
                )
                if condition is not None
            ]
            referenced_rule_ids = [
                rule_id_by_signature[_rule_signature(condition)]
                for condition in conditions
                if _rule_signature(condition) in rule_id_by_signature
            ]
        if len(dict.fromkeys(referenced_rule_ids)) < 2:
            normalized.append(_disabled_resonance(resonance_id, resonance_name, bonus, conditions))
            continue
        normalized.append(
            {
                "id": resonance_id,
                "name": resonance_name,
                "rule_ids": list(dict.fromkeys(referenced_rule_ids)),
                "bonus": round(bonus, 2),
                "enabled": bool(raw.get("enabled", True)),
            }
        )
    return normalized


def _engine_for_indicator(indicator_id: str) -> Optional[str]:
    if indicator_id.startswith("trend_"):
        return "trend_resonance"
    if indicator_id.startswith("platform_setup"):
        return "platform_setup"
    if indicator_id.startswith("platform_"):
        return "platform_breakout"
    return None


def _normalize_analysis_engines(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item) in ANALYSIS_ENGINES]


def _infer_analysis_engines(strategy: Dict[str, Any], legacy_signal_mode: Any = None) -> List[str]:
    engines = set(_normalize_analysis_engines(strategy.get("analysis_engines")))
    legacy_engine = LEGACY_SIGNAL_MODE_FEATURE_GROUPS.get(str(legacy_signal_mode or ""))
    if legacy_engine:
        engines.add(legacy_engine)
    for rule in strategy.get("strategy_rules") or []:
        engine = _engine_for_indicator(str(rule.get("indicator_id") or ""))
        if engine:
            engines.add(engine)
    rules_by_id = {str(rule.get("id") or ""): rule for rule in strategy.get("strategy_rules") or []}
    for resonance in strategy.get("strategy_resonances") or []:
        for rule_id in resonance.get("rule_ids") or []:
            rule = rules_by_id.get(str(rule_id))
            engine = _engine_for_indicator(str((rule or {}).get("indicator_id") or ""))
            if engine:
                engines.add(engine)
    return [engine for engine in ANALYSIS_ENGINES if engine in engines]


SYSTEM_PRESETS = [
    {
        "id": "system-momentum",
        "name": "突破回踩",
        "is_default": True,
        "config": DEFAULT_STRATEGY_CONFIG,
    },
    {
        "id": "system-pullback",
        "name": "趋势回踩观察",
        "is_default": False,
        "config": {
            **DEFAULT_STRATEGY_CONFIG,
            "signal_mode": "breakout_or_pullback",
            "breakout_pullback_direction": "pullback",
            "min_rps20": 60.0,
            "volume_ratio_min": 0.8,
            "max_ma_distance": 0.08,
            "pullback_tolerance": 0.05,
        },
    },
    {
        "id": "system-platform-breakout",
        "name": "平台突破",
        "is_default": False,
        "config": {
            **DEFAULT_STRATEGY_CONFIG,
            "signal_mode": "platform_breakout",
            "trend_filter": "none",
            "min_rps20": None,
            "max_turnover": None,
            "min_pct_chg": 5.0,
            "max_pct_chg": None,
            "volume_ratio_min": None,
            "max_ma_distance": None,
            "max_amplitude": None,
        },
    },
    {
        "id": "system-platform-setup",
        "name": "平台临界",
        "is_default": False,
        "config": {
            **DEFAULT_STRATEGY_CONFIG,
            "signal_mode": "platform_setup",
            "min_rps20": 60.0,
            "volume_ratio_min": None,
            "max_ma_distance": 0.1,
            "min_pct_chg": -3.0,
            "max_pct_chg": 6.0,
        },
    },
    {
        "id": "system-trend-resonance",
        "name": "趋势共振",
        "is_default": False,
        "config": {
            **DEFAULT_STRATEGY_CONFIG,
            "signal_mode": "trend_resonance",
            "analysis_mode": "score",
            "trend_filter": "none",
            "min_rps20": 60.0,
            "min_pct_chg": -3.0,
            "max_pct_chg": 8.0,
            "volume_ratio_min": None,
            "max_ma_distance": None,
            "sort_by": "signal_score",
        },
    },
]

STRATEGY_VERSIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS strategy_versions (
    id TEXT PRIMARY KEY,
    preset_id TEXT,
    strategy_name TEXT,
    version_number INTEGER,
    config_hash TEXT,
    config_json TEXT,
    summary TEXT,
    created_at TIMESTAMP,
    UNIQUE (preset_id, version_number)
)
"""

STRATEGY_VERSION_COLUMNS = [
    "id",
    "preset_id",
    "strategy_name",
    "version_number",
    "config_hash",
    "config_json",
    "summary",
    "created_at",
]


def insert_strategy_versions(db: Database, rows: List[Dict[str, Any]]) -> int:
    inserted = 0
    if not rows:
        return inserted
    db.execute(STRATEGY_VERSIONS_TABLE_SQL, write=True)
    placeholders = ", ".join(["?"] * len(STRATEGY_VERSION_COLUMNS))
    column_sql = ", ".join(STRATEGY_VERSION_COLUMNS)
    insert_sql = f"INSERT INTO strategy_versions ({column_sql}) VALUES ({placeholders})"
    for row in rows:
        if db.scalar(
            """
            SELECT 1
            FROM strategy_versions
            WHERE preset_id = ? AND version_number = ?
            LIMIT 1
            """,
            [row["preset_id"], row["version_number"]],
        ):
            continue
        db.execute(
            insert_sql,
            [row.get(column) for column in STRATEGY_VERSION_COLUMNS],
            write=True,
        )
        inserted += 1
    return inserted


def normalize_strategy_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw_config = config or {}
    merged = {**DEFAULT_STRATEGY_CONFIG, **raw_config}
    merged["strategy_rules"] = _normalize_strategy_rules(merged.get("strategy_rules"))
    merged["strategy_resonances"] = _normalize_strategy_resonances(merged.get("strategy_resonances"), merged["strategy_rules"])
    unmatched_resonance_count = sum(
        1
        for resonance in merged["strategy_resonances"]
        if resonance.get("source") == "legacy_unmatched"
    )
    migration = _migration_info(raw_config, unmatched_strategy_resonance_count=unmatched_resonance_count)
    if migration and unmatched_resonance_count:
        for resonance in merged["strategy_resonances"]:
            warning = resonance.get("migration_warning")
            if resonance.get("source") == "legacy_unmatched" and warning:
                migration["warnings"].append(str(warning))
    raw_signal_mode = raw_config.get("signal_mode")
    if raw_signal_mode in {"breakout", "pullback"}:
        if not raw_config.get("breakout_pullback_direction"):
            merged["breakout_pullback_direction"] = str(raw_signal_mode)
    merged["signal_mode"] = FEATURE_DRIVEN_SIGNAL_MODE
    merged["strategy_interactions"] = []
    if migration:
        merged["migration"] = migration
    elif isinstance(raw_config.get("migration"), dict):
        merged["migration"] = raw_config["migration"]
    if merged.get("breakout_pullback_direction") not in {"both", "breakout", "pullback"}:
        merged["breakout_pullback_direction"] = "both"
    merged["ma_short_window"] = max(3, int(merged["ma_short_window"]))
    merged["ma_long_window"] = max(merged["ma_short_window"] + 1, int(merged["ma_long_window"]))
    merged["platform_lookback_days"] = max(10, int(merged["platform_lookback_days"]))
    merged["platform_setup_lookback_days"] = max(10, int(merged["platform_setup_lookback_days"]))
    merged["trend_ema_fast_window"] = max(2, int(merged["trend_ema_fast_window"]))
    merged["trend_ema_mid_window"] = max(merged["trend_ema_fast_window"] + 1, int(merged["trend_ema_mid_window"]))
    merged["trend_ema_long_window"] = max(merged["trend_ema_mid_window"] + 1, int(merged["trend_ema_long_window"]))
    merged["trend_macd_fast"] = max(2, int(merged["trend_macd_fast"]))
    merged["trend_macd_slow"] = max(merged["trend_macd_fast"] + 1, int(merged["trend_macd_slow"]))
    merged["trend_macd_signal"] = max(2, int(merged["trend_macd_signal"]))
    merged["trend_stoch_window"] = max(5, int(merged["trend_stoch_window"]))
    merged["trend_stoch_k_smooth"] = max(1, int(merged["trend_stoch_k_smooth"]))
    merged["trend_stoch_d_smooth"] = max(1, int(merged["trend_stoch_d_smooth"]))
    if merged.get("trend_entry_signal") not in {"any", "thunder", "follow", "stealth"}:
        merged["trend_entry_signal"] = "any"
    if merged.get("trend_macd_mode") not in {"off", "dif_above_dea", "dif_above_zero", "dif_dea_above_zero"}:
        merged["trend_macd_mode"] = "dif_above_dea"
    if merged.get("trend_stoch_mode") not in {"off", "k_above_d", "cross_up"}:
        merged["trend_stoch_mode"] = "k_above_d"
    if merged.get("platform_range_basis") not in {"high_low", "close"}:
        merged["platform_range_basis"] = "high_low"
    if merged.get("platform_breakout_clearance_mode") not in {"must", "score", "off"}:
        merged["platform_breakout_clearance_mode"] = (
            "must" if merged.get("platform_breakout_require_close_above", True) else "off"
        )
    if merged.get("platform_breakout_max_clearance_mode") not in {"must", "score", "off"}:
        merged["platform_breakout_max_clearance_mode"] = "score"
    if merged.get("platform_breakout_first_mode") not in {"must", "score", "off"}:
        merged["platform_breakout_first_mode"] = "must"
    if merged.get("platform_max_range_mode") not in {"must", "score", "off"}:
        merged["platform_max_range_mode"] = "must"
    if merged.get("platform_bullish_ratio_mode") not in {"must", "score", "off"}:
        merged["platform_bullish_ratio_mode"] = "must"
    if merged.get("platform_bull_volume_advantage_mode") not in {"must", "score", "off"}:
        merged["platform_bull_volume_advantage_mode"] = "must"
    if merged.get("platform_breakout_volume_ratio_mode") not in {"must", "score", "off"}:
        merged["platform_breakout_volume_ratio_mode"] = "must"
    if merged.get("platform_breakout_pct_chg_mode") not in {"must", "score", "off"}:
        merged["platform_breakout_pct_chg_mode"] = "must"
    if merged.get("platform_breakout_bullish_mode") not in {"must", "score", "off"}:
        merged["platform_breakout_bullish_mode"] = "must"
    if merged.get("platform_body_strength_mode") not in {"must", "score", "off"}:
        merged["platform_body_strength_mode"] = "must"
    if merged.get("platform_ma_bullish_mode") not in {"must", "score", "off"}:
        merged["platform_ma_bullish_mode"] = "score"
    if merged.get("platform_ma_rising_mode") not in {"must", "score", "off"}:
        merged["platform_ma_rising_mode"] = "score"
    if merged.get("platform_macd_filter_mode") not in {"must", "score", "off"}:
        merged["platform_macd_filter_mode"] = "score"
    merged["candidate_limit"] = max(1, min(500, int(merged["candidate_limit"])))
    merged["resonance_bonus_cap"] = max(0, min(50, int(_coerce_number(merged.get("resonance_bonus_cap")) or 15)))
    merged["sort_by"] = merged.get("sort_by") or "signal_score"
    merged["macd_position"] = merged.get("macd_position") or "dif_dea_above_zero"
    if merged.get("platform_setup_macd_mode") not in {"none", "dif_above_dea", "dif_above_zero"}:
        merged["platform_setup_macd_mode"] = "dif_above_dea"
    if merged.get("analysis_mode") not in {"strict", "score"}:
        merged["analysis_mode"] = "strict"
    legacy_signal_for_engines = None if raw_config.get("version") == 2 else raw_signal_mode
    merged["analysis_engines"] = _infer_analysis_engines(merged, legacy_signal_for_engines)
    return merged


def _migration_info(config: Dict[str, Any], unmatched_strategy_resonance_count: int = 0) -> Optional[Dict[str, Any]]:
    if not config:
        return None
    preserved_fields = [
        field
        for field in config
        if field in DEFAULT_STRATEGY_CONFIG
        and field not in {"signal_mode", "strategy_interactions", "signal_profile"}
    ]
    dropped_fields: List[str] = []
    warnings: List[str] = []
    raw_signal_mode = config.get("signal_mode")
    if raw_signal_mode and raw_signal_mode != FEATURE_DRIVEN_SIGNAL_MODE:
        dropped_fields.append("signal_mode")
        warnings.append("旧信号模式已转换为特征驱动策略；运行时不再按信号模式分支。")
    if config.get("strategy_interactions"):
        dropped_fields.append("strategy_interactions")
        warnings.append("旧组合倍率已丢弃；新引擎使用显式评分和风险项，不再应用隐藏乘数。")
    profile = config.get("signal_profile")
    if isinstance(profile, dict) and profile.get("rule_groups"):
        dropped_fields.append("signal_profile.rule_groups")
        warnings.append("旧信号模板中的组合规则仅保留为迁移记录，不再参与执行。")
    if unmatched_strategy_resonance_count > 0:
        dropped_fields.append("strategy_resonances.unmatched")
        warnings.append(f"{unmatched_strategy_resonance_count} 个旧组合共振无法匹配已有规则，已停止参与执行。")
    if not dropped_fields and not warnings:
        return None
    return {
        "from_version": 1,
        "migrated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "preserved_fields": sorted(set(preserved_fields)),
        "dropped_fields": sorted(set(dropped_fields)),
        "warnings": warnings,
    }


class StrategyService:
    def __init__(self, db: Database):
        self.db = db

    def list_presets(self) -> List[Dict[str, Any]]:
        rows = self.db.query(
            """
            SELECT *
            FROM strategy_presets
            WHERE deleted_at IS NULL
            ORDER BY is_default DESC, is_system DESC, updated_at DESC
            """
        )
        latest_versions = self._latest_versions()
        for row in rows:
            row["config"] = normalize_strategy_config(json.loads(row.pop("config_json") or "{}"))
            version = latest_versions.get(row["id"])
            row["latest_version_id"] = version.get("id") if version else None
            row["latest_version_number"] = version.get("version_number") if version else None
            row["latest_version_summary"] = version.get("summary") if version else _strategy_summary(row["config"])
        return rows

    def default_config(self) -> Dict[str, Any]:
        row = self.db.query(
            """
            SELECT config_json
            FROM strategy_presets
            WHERE is_default = TRUE
              AND deleted_at IS NULL
            ORDER BY updated_at DESC
            LIMIT 1
            """
        )
        if not row:
            return normalize_strategy_config(DEFAULT_STRATEGY_CONFIG)
        return normalize_strategy_config(json.loads(row[0]["config_json"] or "{}"))

    def get_preset(self, preset_id: str) -> Optional[Dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM strategy_presets WHERE id = ? AND deleted_at IS NULL",
            [preset_id],
        )
        if not rows:
            return None
        row = rows[0]
        row["config"] = normalize_strategy_config(json.loads(row.pop("config_json") or "{}"))
        version = self._latest_versions([preset_id]).get(preset_id)
        row["latest_version_id"] = version.get("id") if version else None
        row["latest_version_number"] = version.get("version_number") if version else None
        row["latest_version_summary"] = version.get("summary") if version else _strategy_summary(row["config"])
        return row

    def list_versions(self, preset_id: str) -> List[Dict[str, Any]]:
        try:
            self._ensure_versions_table()
            rows = self.db.query(
                """
                SELECT *
                FROM strategy_versions
                WHERE preset_id = ?
                ORDER BY version_number DESC
                """,
                [preset_id],
            )
        except duckdb.Error:
            return []
        for row in rows:
            row["config"] = normalize_strategy_config(json.loads(row.pop("config_json") or "{}"))
        return rows

    def save_preset(
        self,
        name: str,
        config: Dict[str, Any],
        preset_id: Optional[str] = None,
        set_default: bool = False,
    ) -> Dict[str, Any]:
        now = datetime.utcnow()
        target_id = preset_id or f"custom-{uuid.uuid4().hex[:12]}"
        existing = self.get_preset(target_id)
        if existing and existing.get("is_system"):
            target_id = f"custom-{uuid.uuid4().hex[:12]}"
        if set_default:
            self.db.execute("UPDATE strategy_presets SET is_default = FALSE", write=True)
        normalized_config = normalize_strategy_config(config)
        row = {
            "id": target_id,
            "name": name.strip() or "未命名策略",
            "config_json": json.dumps(normalized_config, ensure_ascii=False),
            "is_system": False,
            "is_default": set_default,
            "created_at": existing.get("created_at") if existing else now,
            "updated_at": now,
            "deleted_at": None,
        }
        self.db.upsert("strategy_presets", [row], ["id"])
        self._record_version_if_changed(target_id, row["name"], normalized_config, now)
        return self.get_preset(target_id) or row

    def delete_preset(self, preset_id: str) -> bool:
        preset = self.get_preset(preset_id)
        if not preset or preset.get("is_system"):
            return False
        self.db.execute(
            """
            UPDATE strategy_presets
            SET deleted_at = ?, is_default = FALSE, updated_at = ?
            WHERE id = ?
            """,
            [datetime.utcnow(), datetime.utcnow(), preset_id],
            write=True,
        )
        if preset.get("is_default"):
            self.db.execute(
                """
                UPDATE strategy_presets
                SET is_default = TRUE, deleted_at = NULL, updated_at = ?
                WHERE id = 'system-momentum'
                """,
                [datetime.utcnow()],
                write=True,
            )
        return True

    def set_default(self, preset_id: str) -> bool:
        if not self.get_preset(preset_id):
            return False
        self.db.execute("UPDATE strategy_presets SET is_default = FALSE", write=True)
        self.db.execute(
            "UPDATE strategy_presets SET is_default = TRUE, updated_at = ? WHERE id = ?",
            [datetime.utcnow(), preset_id],
            write=True,
        )
        return True

    def restore_system_defaults(self) -> List[Dict[str, Any]]:
        self.db.execute("UPDATE strategy_presets SET is_default = FALSE", write=True)
        now = datetime.utcnow()
        for preset in SYSTEM_PRESETS:
            self.db.upsert(
                "strategy_presets",
                [
                    {
                        "id": preset["id"],
                        "name": preset["name"],
                        "config_json": json.dumps(preset["config"], ensure_ascii=False),
                        "is_system": True,
                        "is_default": preset.get("is_default", False),
                        "created_at": now,
                        "updated_at": now,
                        "deleted_at": None,
                    }
                ],
                ["id"],
            )
        return self.list_presets()

    def _latest_versions(self, preset_ids: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        params: List[Any] = []
        where = ""
        if preset_ids:
            placeholders = ", ".join(["?"] * len(preset_ids))
            where = f"WHERE preset_id IN ({placeholders})"
            params.extend(preset_ids)
        try:
            self._ensure_versions_table()
            rows = self.db.query(
                f"""
                SELECT *
                FROM (
                    SELECT *,
                           ROW_NUMBER() OVER (PARTITION BY preset_id ORDER BY version_number DESC) AS version_rank
                    FROM strategy_versions
                    {where}
                )
                WHERE version_rank = 1
                """,
                params,
            )
        except duckdb.Error:
            return {}
        return {row["preset_id"]: row for row in rows}

    def _record_version_if_changed(
        self,
        preset_id: str,
        strategy_name: str,
        config: Dict[str, Any],
        now: datetime,
    ) -> None:
        try:
            self._ensure_versions_table()
        except duckdb.Error:
            return
        config_hash = _config_hash(config)
        latest = self._latest_versions([preset_id]).get(preset_id)
        if latest and latest.get("config_hash") == config_hash:
            return
        version_number = int(latest.get("version_number") or 0) + 1 if latest else 1
        try:
            insert_strategy_versions(
                self.db,
                [
                    {
                        "id": f"version-{uuid.uuid4().hex[:12]}",
                        "preset_id": preset_id,
                        "strategy_name": strategy_name,
                        "version_number": version_number,
                        "config_hash": config_hash,
                        "config_json": json.dumps(config, ensure_ascii=False),
                        "summary": _strategy_summary(config),
                        "created_at": now,
                    }
                ],
            )
        except duckdb.Error:
            return

    def _ensure_versions_table(self) -> None:
        self.db.execute(STRATEGY_VERSIONS_TABLE_SQL, write=True)


def _config_hash(config: Dict[str, Any]) -> str:
    canonical = json.dumps(_config_for_hash(normalize_strategy_config(config)), ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


def _config_for_hash(config: Dict[str, Any]) -> Dict[str, Any]:
    stable = json.loads(json.dumps(config, ensure_ascii=False))
    migration = stable.get("migration")
    if isinstance(migration, dict):
        migration.pop("migrated_at", None)
    return stable


def _strategy_summary(config: Dict[str, Any]) -> str:
    normalized = normalize_strategy_config(config)
    parts = [
        "特征驱动",
        f"成交额≥{_money(normalized['min_amount'])}",
        f"RPS{normalized['rps_window']}",
        f"MA{normalized['ma_short_window']}/{normalized['ma_long_window']}",
    ]
    if normalized.get("platform_setup_max_distance_to_high") != DEFAULT_STRATEGY_CONFIG["platform_setup_max_distance_to_high"]:
        parts.append(f"距上沿≤{_pct(normalized['platform_setup_max_distance_to_high'])}")
    if normalized.get("platform_breakout_clearance") != DEFAULT_STRATEGY_CONFIG["platform_breakout_clearance"]:
        parts.append(f"突破≥{_pct(normalized['platform_breakout_clearance'])}")
    if normalized.get("min_topic_heat") is not None:
        parts.append(f"题材热度≥{normalized['min_topic_heat']:g}")
    return " · ".join(parts)


def _pct(value: Any) -> str:
    try:
        text = f"{float(value) * 100:.2f}".rstrip("0").rstrip(".")
        return f"{text}%"
    except (TypeError, ValueError):
        return "-"


def _money(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if abs(number) >= 100_000_000:
        return f"{number / 100_000_000:g}亿"
    if abs(number) >= 10_000:
        return f"{number / 10_000:g}万"
    return f"{number:g}"
