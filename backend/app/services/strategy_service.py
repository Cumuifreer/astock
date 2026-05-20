from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.app.db import Database


DEFAULT_STRATEGY_CONFIG: Dict[str, Any] = {
    "min_price": 4.0,
    "min_amount": 80_000_000,
    "min_float_market_value": None,
    "max_float_market_value": None,
    "ma_short_window": 20,
    "ma_long_window": 60,
    "trend_filter": "ma_short_above_long",
    "signal_mode": "breakout_or_pullback",
    "breakout_lookback": 20,
    "pullback_tolerance": 0.035,
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
    "candidate_limit": 50,
    "sort_by": "signal_score",
    "missing_float_market_value_policy": "allow",
    "include_bj": False,
    "exclude_star_board": False,
}


SYSTEM_PRESETS = [
    {
        "id": "system-momentum",
        "name": "右侧强势突破",
        "is_default": True,
        "config": DEFAULT_STRATEGY_CONFIG,
    },
    {
        "id": "system-pullback",
        "name": "趋势回踩观察",
        "is_default": False,
        "config": {
            **DEFAULT_STRATEGY_CONFIG,
            "signal_mode": "pullback",
            "min_rps20": 60.0,
            "volume_ratio_min": 0.8,
            "max_ma_distance": 0.08,
            "pullback_tolerance": 0.05,
        },
    },
]


def normalize_strategy_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = {**DEFAULT_STRATEGY_CONFIG, **(config or {})}
    merged["ma_short_window"] = max(3, int(merged["ma_short_window"]))
    merged["ma_long_window"] = max(merged["ma_short_window"] + 1, int(merged["ma_long_window"]))
    merged["candidate_limit"] = max(1, min(500, int(merged["candidate_limit"])))
    merged["sort_by"] = merged.get("sort_by") or "signal_score"
    return merged


class StrategyService:
    def __init__(self, db: Database):
        self.db = db

    def list_presets(self) -> List[Dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM strategy_presets ORDER BY is_default DESC, is_system DESC, updated_at DESC"
        )
        for row in rows:
            row["config"] = json.loads(row.pop("config_json") or "{}")
        return rows

    def default_config(self) -> Dict[str, Any]:
        row = self.db.query(
            "SELECT config_json FROM strategy_presets WHERE is_default = TRUE ORDER BY updated_at DESC LIMIT 1"
        )
        if not row:
            return normalize_strategy_config(DEFAULT_STRATEGY_CONFIG)
        return normalize_strategy_config(json.loads(row[0]["config_json"] or "{}"))

    def get_preset(self, preset_id: str) -> Optional[Dict[str, Any]]:
        rows = self.db.query("SELECT * FROM strategy_presets WHERE id = ?", [preset_id])
        if not rows:
            return None
        row = rows[0]
        row["config"] = normalize_strategy_config(json.loads(row.pop("config_json") or "{}"))
        return row

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
        row = {
            "id": target_id,
            "name": name.strip() or "未命名策略",
            "config_json": json.dumps(normalize_strategy_config(config), ensure_ascii=False),
            "is_system": False,
            "is_default": set_default,
            "created_at": existing.get("created_at") if existing else now,
            "updated_at": now,
        }
        self.db.upsert("strategy_presets", [row], ["id"])
        return self.get_preset(target_id) or row

    def delete_preset(self, preset_id: str) -> bool:
        preset = self.get_preset(preset_id)
        if not preset or preset.get("is_system"):
            return False
        self.db.execute("DELETE FROM strategy_presets WHERE id = ?", [preset_id], write=True)
        if preset.get("is_default"):
            self.db.execute(
                "UPDATE strategy_presets SET is_default = TRUE WHERE id = 'system-momentum'",
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
                    }
                ],
                ["id"],
            )
        return self.list_presets()
