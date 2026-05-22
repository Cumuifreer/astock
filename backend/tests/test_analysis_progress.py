from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.analysis_service import AnalysisService
from backend.app.services.strategy_service import DEFAULT_STRATEGY_CONFIG
from backend.app.services.update_service import UpdateService


def test_analysis_service_reports_fine_grained_progress(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    events = []

    AnalysisService(db).run(
        DEFAULT_STRATEGY_CONFIG,
        progress=lambda stage, processed, total: events.append((stage, processed, total)),
    )

    assert events[0] == ("读取本地行情", 1, 7)
    assert ("应用策略条件", 5, 7) in events
    assert ("保存分析报告", 6, 7) in events


def test_update_service_analysis_task_uses_progress_callback(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    task_id = "analyze-test"
    service._write_task(
        task_id,
        kind="analyze",
        status="running",
        stage="准备分析",
        source="本地仓库",
        current_stock=None,
        total=0,
        processed=0,
        success=0,
        failed=0,
        skipped=0,
        warning=None,
        summary={},
        error_message=None,
    )
    patches = []
    original_patch = service._patch_task

    def record_patch(task_id, **changes):
        patches.append(changes.copy())
        original_patch(task_id, **changes)

    class Runner:
        def run(self, config, progress):
            progress("计算技术指标", 3, 7)
            progress("生成候选结果", 5, 7)
            return "analysis-run"

    service._patch_task = record_patch
    service._run_analysis(task_id, DEFAULT_STRATEGY_CONFIG, Runner())

    stages = [item.get("stage") for item in patches]
    assert "计算技术指标" in stages
    assert "生成候选结果" in stages
    assert patches[-1]["stage"] == "分析完成"
    assert patches[-1]["processed"] == 7
    assert patches[-1]["total"] == 7
