from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.signal_mode_service import SignalModeService


def test_signal_mode_service_persists_editable_modes(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = SignalModeService(db)
    service.ensure_seeded()

    mode = service.list_modes()[0]
    mode["name"] = "我的突破模式"
    mode["note"] = "直接编辑初始模式，不区分系统模板。"
    saved = service.save_mode(mode)

    assert saved["name"] == "我的突破模式"
    assert saved["note"] == "直接编辑初始模式，不区分系统模板。"
    assert service.get_mode(saved["id"])["name"] == "我的突破模式"


def test_signal_mode_service_creates_and_deletes_blank_mode(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = SignalModeService(db)
    service.ensure_seeded()

    created = service.create_mode("自定义模式")

    assert created["id"].startswith("mode-")
    assert created["name"] == "自定义模式"
    assert [field["indicator_id"] for field in created["fields"]] == [
        "min_price",
        "min_amount",
        "min_float_market_value",
        "max_float_market_value",
        "include_bj",
        "exclude_star_board",
        "missing_turnover_policy",
        "missing_float_market_value_policy",
    ]

    assert service.delete_mode(created["id"]) is True
    assert service.get_mode(created["id"]) is None
