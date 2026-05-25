import json

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.strategy_service import StrategyService, normalize_strategy_config


def test_signal_presets_are_independent_from_strategy_presets(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = StrategyService(db)

    before_strategy_ids = {preset["id"] for preset in service.list_presets()}
    created = service.save_signal_preset(
        name="我的平台模板",
        description="只负责填参数，不是策略",
        config={"signal_mode": "platform_breakout", "platform_breakout_enabled": True},
    )
    updated = service.save_signal_preset(
        name="我的平台模板 v2",
        description="改过参数",
        config={"signal_mode": "platform_breakout", "platform_breakout_enabled": True, "platform_max_range": 0.1},
        preset_id=created["id"],
    )

    after_strategy_ids = {preset["id"] for preset in service.list_presets()}
    signal_ids = {preset["id"] for preset in service.list_signal_presets()}

    assert before_strategy_ids == after_strategy_ids
    assert created["id"] == updated["id"]
    assert updated["name"] == "我的平台模板 v2"
    assert updated["description"] == "改过参数"
    assert updated["is_system"] is False
    assert updated["config"]["platform_breakout_enabled"] is True
    assert updated["config"]["platform_max_range"] == 0.1
    assert created["id"] in signal_ids


def test_signal_presets_seed_system_rows_and_custom_delete_only(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = StrategyService(db)

    system = next(preset for preset in service.list_signal_presets() if preset["id"] == "signal-platform-breakout")
    custom = service.save_signal_preset("临时模板", "", {"platform_setup_enabled": True})

    assert system["is_system"] is True
    assert service.delete_signal_preset(system["id"]) is False
    assert service.delete_signal_preset(custom["id"]) is True
    assert custom["id"] not in {preset["id"] for preset in service.list_signal_presets()}


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
    assert old["config"]["platform_breakout_clearance_mode"] == "must"
    assert old["config"]["platform_breakout_clearance"] == 0.03
    assert old["config"]["platform_breakout_max_clearance"] == 0.08
    assert old["config"]["platform_breakout_max_clearance_mode"] == "score"
    assert old["config"]["platform_breakout_first_mode"] == "must"
    assert old["config"]["platform_bullish_ratio_score"] == 0.6
    assert old["config"]["platform_bull_volume_advantage_score"] == 1.2
    assert old["config"]["platform_ma_bullish_mode"] == "score"
    assert old["config"]["platform_ma_rising_mode"] == "score"
    assert old["config"]["platform_macd_filter_mode"] == "score"


def test_normalize_legacy_breakout_modes_to_unified_mode():
    breakout = normalize_strategy_config({"signal_mode": "breakout"})
    pullback = normalize_strategy_config({"signal_mode": "pullback"})
    combined = normalize_strategy_config({"signal_mode": "breakout_or_pullback"})

    assert breakout["signal_mode"] == "breakout_or_pullback"
    assert breakout["breakout_pullback_direction"] == "breakout"
    assert pullback["signal_mode"] == "breakout_or_pullback"
    assert pullback["breakout_pullback_direction"] == "pullback"
    assert combined["breakout_pullback_direction"] == "both"
    assert normalize_strategy_config({"signal_mode": "trend_resonance"})["trend_ema_long_window"] == 60


def test_migrate_refreshes_system_template_config_without_resetting_user_default(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "strategy_presets",
        [
            {
                "id": "custom-default",
                "name": "我的默认",
                "config_json": json.dumps({"signal_mode": "platform_breakout"}, ensure_ascii=False),
                "is_system": False,
                "is_default": True,
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            },
            {
                "id": "system-platform-breakout",
                "name": "平台突破",
                "config_json": json.dumps(
                    {
                        "signal_mode": "platform_breakout",
                        "platform_breakout_clearance": 0.0,
                        "platform_breakout_first_mode": "score",
                    },
                    ensure_ascii=False,
                ),
                "is_system": True,
                "is_default": False,
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            },
        ],
        ["id"],
    )

    migrate(db)

    rows = db.query("SELECT id, config_json, is_default FROM strategy_presets")
    by_id = {row["id"]: row for row in rows}
    breakout = json.loads(by_id["system-platform-breakout"]["config_json"])
    assert breakout["platform_breakout_clearance"] == 0.03
    assert breakout["platform_breakout_first_mode"] == "must"
    assert by_id["custom-default"]["is_default"] is True


def test_delete_preset_soft_deletes_and_hides_from_lists(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = StrategyService(db)
    preset = service.save_preset("待删除策略", {"signal_mode": "platform_setup"}, set_default=True)

    assert service.delete_preset(preset["id"]) is True

    deleted = db.query("SELECT id, deleted_at, is_default FROM strategy_presets WHERE id = ?", [preset["id"]])
    assert deleted
    assert deleted[0]["deleted_at"] is not None
    assert deleted[0]["is_default"] is False
    assert preset["id"] not in [row["id"] for row in service.list_presets()]
    assert service.get_preset(preset["id"]) is None
    assert service.default_config()["signal_mode"] == "breakout_or_pullback"


def test_list_presets_ignores_rows_deleted_before_migration(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "strategy_presets",
        [
            {
                "id": "custom-deleted",
                "name": "旧删除策略",
                "config_json": json.dumps({"signal_mode": "platform_breakout"}, ensure_ascii=False),
                "is_system": False,
                "is_default": False,
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
                "deleted_at": "2026-01-02T00:00:00",
            }
        ],
        ["id"],
    )

    presets = StrategyService(db).list_presets()

    assert "custom-deleted" not in [preset["id"] for preset in presets]


def test_save_preset_records_versions_only_when_config_changes(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = StrategyService(db)

    first = service.save_preset("平台临界", {"signal_mode": "platform_setup"})
    same = service.save_preset("平台临界改名", {"signal_mode": "platform_setup"}, preset_id=first["id"])
    changed = service.save_preset(
        "平台临界改名",
        {"signal_mode": "platform_setup", "platform_setup_max_distance_to_high": 0.02},
        preset_id=first["id"],
    )

    versions = service.list_versions(first["id"])
    presets = service.list_presets()
    preset = next(row for row in presets if row["id"] == first["id"])

    assert same["id"] == first["id"] == changed["id"]
    assert [version["version_number"] for version in versions] == [2, 1]
    assert versions[0]["strategy_name"] == "平台临界改名"
    assert "距上沿" in versions[0]["summary"]
    assert preset["latest_version_number"] == 2
    assert preset["latest_version_id"] == versions[0]["id"]


def test_save_preset_recreates_missing_version_table_and_records_version(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.execute("DROP TABLE strategy_versions", write=True)
    service = StrategyService(db)

    preset = service.save_preset("临时策略", {"signal_mode": "platform_setup"})
    versions = service.list_versions(preset["id"])

    assert preset["id"].startswith("custom-")
    assert preset["name"] == "临时策略"
    assert preset["latest_version_number"] == 1
    assert [version["version_number"] for version in versions] == [1]


def test_save_preset_records_version_without_generic_version_upsert(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    original_upsert = db.upsert

    def guarded_upsert(table, rows, key_columns):
        if table == "strategy_versions":
            raise AssertionError("strategy version writes must not use generic upsert")
        return original_upsert(table, rows, key_columns)

    monkeypatch.setattr(db, "upsert", guarded_upsert)
    service = StrategyService(db)

    preset = service.save_preset("临时策略", {"signal_mode": "platform_setup"})
    versions = service.list_versions(preset["id"])

    assert preset["latest_version_number"] == 1
    assert [version["version_number"] for version in versions] == [1]


def test_migrate_backfills_initial_version_for_existing_custom_presets(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "strategy_presets",
        [
            {
                "id": "custom-existing",
                "name": "已有策略",
                "config_json": json.dumps({"signal_mode": "platform_breakout"}, ensure_ascii=False),
                "is_system": False,
                "is_default": False,
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-02T00:00:00",
                "deleted_at": None,
            }
        ],
        ["id"],
    )
    original_upsert = db.upsert

    def guarded_upsert(table, rows, key_columns):
        if table == "strategy_versions":
            raise AssertionError("strategy version writes must not use generic upsert")
        return original_upsert(table, rows, key_columns)

    monkeypatch.setattr(db, "upsert", guarded_upsert)

    migrate(db)
    preset = StrategyService(db).get_preset("custom-existing")
    versions = StrategyService(db).list_versions("custom-existing")

    assert preset["latest_version_number"] == 1
    assert versions[0]["strategy_name"] == "已有策略"
