import json

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.strategy_service import StrategyService


def test_list_presets_normalizes_missing_new_fields(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "strategy_presets",
        [
            {
                "id": "custom-old",
                "name": "旧策略",
                "config_json": json.dumps({"signal_mode": "platform_breakout"}, ensure_ascii=False),
                "is_system": False,
                "is_default": True,
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            }
        ],
        ["id"],
    )

    presets = StrategyService(db).list_presets()
    old = next(preset for preset in presets if preset["id"] == "custom-old")

    assert old["config"]["platform_range_basis"] == "high_low"
    assert old["config"]["platform_breakout_require_close_above"] is True
    assert old["config"]["platform_breakout_clearance"] == 0.0
