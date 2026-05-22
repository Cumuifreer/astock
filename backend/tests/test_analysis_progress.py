from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.analysis_service import AnalysisService
from backend.app.services.data_service import DataService
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


def test_analysis_queue_freezes_submitted_strategy_payload(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())
    config = {**DEFAULT_STRATEGY_CONFIG, "min_price": 4.0}
    task_id = service.start_analysis(config, AnalysisService(db))
    config["min_price"] = 99.0

    row = db.query("SELECT status, payload_json FROM task_runs WHERE id = ?", [task_id])[0]
    assert row["status"] == "queued"
    assert '"min_price": 4.0' in row["payload_json"]
    assert '"min_price": 99.0' not in row["payload_json"]


def test_task_queue_runs_queued_tasks_in_fifo_order(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    seen = []

    service._write_task(
        "update-test",
        kind="update",
        status="queued",
        stage="排队等待",
        source="本地仓库",
        summary={},
        payload={"mode": "daily_light"},
    )
    service._write_task(
        "intraday-test",
        kind="intraday",
        status="queued",
        stage="排队等待",
        source="本地仓库",
        summary={},
        payload={},
    )

    monkeypatch.setattr(service, "_run_update", lambda task_id, payload: seen.append((task_id, payload["mode"])))
    monkeypatch.setattr(service, "_run_intraday_sample", lambda task_id, payload: seen.append((task_id, "intraday")))

    service._drain_queue()

    assert seen == [("update-test", "daily_light"), ("intraday-test", "intraday")]


def test_latest_task_hides_internal_queue_payload(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    service._write_task(
        "analyze-test",
        kind="analyze",
        status="queued",
        stage="排队等待",
        source="本地仓库",
        summary={},
        payload={"config": DEFAULT_STRATEGY_CONFIG},
    )

    task = DataService(db).latest_task("analyze")

    assert task is not None
    assert "payload_json" not in task
    assert "queue_order" not in task
