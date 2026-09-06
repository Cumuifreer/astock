import json
import logging
from contextlib import contextmanager
from datetime import date, datetime, timedelta

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

    run_id = AnalysisService(db).run(
        {**DEFAULT_STRATEGY_CONFIG, "name": "突破回踩"},
        progress=lambda stage, processed, total: events.append((stage, processed, total)),
    )
    summary = json.loads(db.scalar("SELECT summary_json FROM analysis_runs WHERE id = ?", [run_id]) or "{}")

    assert events[0] == ("读取本地行情", 1, 7)
    assert ("应用策略条件", 5, 7) in events
    assert ("保存分析报告", 6, 7) in events
    assert summary["strategy_name"] == "突破回踩"


def test_analysis_service_reports_step_four_heartbeat(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    target = date(2026, 5, 22)
    now = datetime.utcnow()
    db.upsert(
        "historical_bars",
        [
            {
                "code": "000001.SZ",
                "date": target,
                "open": 10.0,
                "high": 10.5,
                "low": 9.8,
                "close": 10.2,
                "prev_close": 10.0,
                "volume": 1000.0,
                "amount": 100000.0,
                "turn": 1.2,
                "pct_chg": 2.0,
                "tradestatus": "1",
                "is_st": False,
                "source": "test",
                "updated_at": now,
            }
        ],
        ["code", "date"],
    )
    events = []

    AnalysisService(db)._build_analysis_frame(
        DEFAULT_STRATEGY_CONFIG,
        as_of_date=target,
        progress=lambda stage, processed, total: events.append((stage, processed, total)),
    )

    assert ("计算技术形态", 4, 7) in events
    assert ("计算技术形态 1/1", 4, 7) in events


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
        def run(self, config, progress, **_kwargs):
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




def test_analysis_task_completion_publishes_result_for_polling(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    task_id = "analyze-completion"
    run_id = "analysis-completion"
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

    class Runner:
        def run(self, config, progress, **_kwargs):
            progress("计算技术形态", 4, 7)
            now = datetime.utcnow()
            db.upsert(
                "analysis_runs",
                [
                    {
                        "id": run_id,
                        "status": "completed_full",
                        "started_at": now,
                        "finished_at": now,
                        "config_json": json.dumps(config, ensure_ascii=False),
                        "summary_json": json.dumps(
                            {"candidate_count": 2, "zero_reason": None, "strategy_name": "完成测试"},
                            ensure_ascii=False,
                        ),
                        "error_message": None,
                    }
                ],
                ["id"],
            )
            db.upsert(
                "candidate_results",
                [
                    {
                        "run_id": run_id,
                        "rank": 1,
                        "code": "000001.SZ",
                        "name": "平安银行",
                        "signal_score": 88.0,
                        "data_sources": "{}",
                        "reasons_json": "[]",
                        "metrics_json": "{}",
                        "created_at": now,
                    },
                    {
                        "run_id": run_id,
                        "rank": 2,
                        "code": "000002.SZ",
                        "name": "万科A",
                        "signal_score": 80.0,
                        "data_sources": "{}",
                        "reasons_json": "[]",
                        "metrics_json": "{}",
                        "created_at": now,
                    },
                ],
                ["run_id", "code"],
            )
            return run_id

    service._run_analysis(task_id, {**DEFAULT_STRATEGY_CONFIG, "strategy_name": "完成测试"}, Runner())

    task = DataService(db).latest_task("analyze")
    report = DataService(db).analysis_report(run_id)
    assert task["status"] == "completed_full"
    assert task["stage"] == "分析完成"
    assert task["processed"] == 7
    assert task["total"] == 7
    assert task["summary"]["analysis_run_id"] == run_id
    assert task["summary"]["candidate_count"] == 2
    assert report["analysis"]["status"] == "completed_full"
    assert len(report["candidates"]["rows"]) == 2


def test_analysis_queue_freezes_submitted_strategy_payload(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())
    config = {**DEFAULT_STRATEGY_CONFIG, "min_price": 4.0}
    task_id, run_id = service.start_analysis(config, AnalysisService(db))
    config["min_price"] = 99.0

    row = db.query("SELECT status, summary_json, payload_json FROM task_runs WHERE id = ?", [task_id])[0]
    summary = json.loads(row["summary_json"] or "{}")
    assert row["status"] == "queued"
    assert summary["analysis_run_id"] == run_id
    assert f'"run_id": "{run_id}"' in row["payload_json"]
    assert '"min_price": 4.0' in row["payload_json"]
    assert '"min_price": 99.0' not in row["payload_json"]


def test_analysis_service_records_preassigned_run_and_task_ids(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)

    run_id = AnalysisService(db).run(
        {**DEFAULT_STRATEGY_CONFIG, "name": "契约测试"},
        run_id="analysis-contract",
        task_id="analyze-contract",
    )

    row = db.query("SELECT id, task_id FROM analysis_runs WHERE id = ?", [run_id])[0]
    assert row["id"] == "analysis-contract"
    assert row["task_id"] == "analyze-contract"


def test_recover_interrupted_tasks_fails_stale_analysis_runs(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    now = datetime.utcnow()
    db.upsert(
        "analysis_runs",
        [
            {
                "id": "analysis-stale",
                "status": "running",
                "started_at": now,
                "finished_at": None,
                "config_json": "{}",
                "summary_json": "{}",
                "error_message": None,
                "task_id": "analyze-stale",
            }
        ],
        ["id"],
    )

    UpdateService(db).recover_interrupted_tasks()

    row = db.query("SELECT status, finished_at, error_message FROM analysis_runs WHERE id = ?", ["analysis-stale"])[0]
    assert row["status"] == "failed"
    assert row["finished_at"] is not None
    assert row["error_message"] == "服务重启后中止"


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
        "analyze-test",
        kind="analyze",
        status="queued",
        stage="排队等待",
        source="本地仓库",
        summary={},
        payload={},
    )

    monkeypatch.setattr(service, "_run_update", lambda task_id, payload: seen.append((task_id, payload["mode"])))
    service.analysis_runner = object()
    monkeypatch.setattr(service, "_run_analysis", lambda task_id, config, runner, **kwargs: seen.append((task_id, "analyze")))

    service._drain_queue()

    assert seen == [("update-test", "daily_light"), ("analyze-test", "analyze")]


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


def test_task_runs_lists_full_active_queue_in_order(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    service._write_task(
        "analyze-queued",
        kind="analyze",
        status="queued",
        stage="准备分析",
        source="本地仓库",
        summary={"rank": 2},
        payload={"secret": "strategy-config"},
        queue_order=20,
    )
    service._write_task(
        "update-running",
        kind="update",
        status="running",
        stage="刷新快照",
        source="Tushare 实时日线",
        summary={"rank": 1},
        payload={"mode": "daily_light"},
    )
    service._write_task(
        "brief-completed",
        kind="brief",
        status="completed_full",
        stage="资讯完成",
        source="多源资讯",
        summary={"rank": 3},
        payload={},
    )

    rows = DataService(db).task_runs(statuses=["queued", "running"], limit=10)

    assert [row["id"] for row in rows] == ["analyze-queued", "update-running"]
    assert rows[0]["summary"] == {"rank": 2}
    assert "payload_json" not in rows[0]
    assert "queue_order" not in rows[0]


def test_task_runs_lists_terminal_tasks_by_latest_time_not_queue_order(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    old_time = datetime(2026, 5, 22, 7, 27, 54)
    new_time = datetime(2026, 6, 3, 13, 10, 0)
    service._write_task(
        "update-old",
        kind="update",
        status="completed_full",
        stage="轻量日更完成",
        source="Tushare",
        summary={},
        payload={"mode": "daily_light"},
        queue_order=1,
        started_at=old_time,
        finished_at=old_time,
    )
    service._write_task(
        "update-new",
        kind="update",
        status="completed_full",
        stage="轻量日更完成",
        source="Tushare",
        summary={},
        payload={"mode": "daily_light"},
        queue_order=2,
        started_at=new_time,
        finished_at=new_time,
    )

    rows = DataService(db).task_runs(statuses=["completed_full", "completed_partial", "failed"], limit=2)

    assert [row["id"] for row in rows] == ["update-new", "update-old"]




def test_core_task_starters_reuse_active_matching_payloads(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())

    update_first = service.start_update({"mode": "daily_light"})
    update_second = service.start_update({"mode": "full", "force": True})
    analyze_first = service.start_analysis({"candidate_limit": 5}, AnalysisService(db))
    analyze_second = service.start_analysis({"candidate_limit": 5}, AnalysisService(db))

    assert update_second == update_first
    assert analyze_second == analyze_first
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'update'") == 1
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'analyze'") == 1


def test_core_task_starters_store_canonical_payload_hashes(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())

    update_id = service.start_update({"mode": "daily_light", "force": False})
    analyze_id, analyze_run = service.start_analysis({"candidate_limit": 5}, AnalysisService(db))

    rows = db.query("SELECT id, payload_hash FROM task_runs ORDER BY id")
    hashes = {row["id"]: row["payload_hash"] for row in rows}

    assert hashes[update_id]
    assert hashes[analyze_id]
    assert service.start_analysis({"candidate_limit": 5}, AnalysisService(db)) == (analyze_id, analyze_run)


def test_analysis_task_runs_without_memory_floor(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    calls = []

    class Runner:
        def run(self, *args, **kwargs):
            calls.append("started")
            return "analysis-low-memory"

    service.configure_runners(analysis_runner=Runner())
    monkeypatch.setattr(service, "_available_memory_mb", lambda: 128, raising=False)
    monkeypatch.setattr(service, "_min_available_memory_mb", lambda: 700, raising=False)
    service._write_task(
        "analyze-low-memory",
        kind="analyze",
        status="queued",
        stage="准备分析",
        source="本地仓库",
        summary={},
        payload={"config": {"candidate_limit": 5}, "run_id": "analysis-low-memory"},
    )

    service._drain_queue()

    row = db.query("SELECT status, stage, warning, error_message FROM task_runs WHERE id = 'analyze-low-memory'")[0]
    assert calls == ["started"]
    assert row["status"] == "completed_full"
    assert row["stage"] == "分析完成"
    assert row["warning"] is None
    assert row["error_message"] is None




def test_next_queued_task_claims_task_once_across_service_instances(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    first_service = UpdateService(db)
    second_service = UpdateService(db)
    first_service._write_task(
        "queued-once",
        kind="update",
        status="queued",
        stage="准备更新",
        source="本地仓库",
        summary={},
        payload={"mode": "daily_light"},
    )

    first_claim = first_service._next_queued_task()
    second_claim = second_service._next_queued_task()

    assert first_claim and first_claim["id"] == "queued-once"
    assert second_claim is None
    assert db.scalar("SELECT status FROM task_runs WHERE id = ?", ["queued-once"]) == "running"


def test_next_queued_task_does_not_require_update_returning(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    service._write_task(
        "queued-compatible",
        kind="update",
        status="queued",
        stage="准备更新",
        source="本地仓库",
        summary={},
        payload={"mode": "daily_light"},
    )
    original_connect = db.connect

    class ReturningUnsupportedConnection:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, params=None):
            if "RETURNING" in str(sql).upper():
                raise RuntimeError("RETURNING is not supported by this DuckDB runtime")
            return self._conn.execute(sql, params or [])

        def __getattr__(self, name):
            return getattr(self._conn, name)

    @contextmanager
    def guarded_connect():
        with original_connect() as conn:
            yield ReturningUnsupportedConnection(conn)

    monkeypatch.setattr(db, "connect", guarded_connect)

    claimed = service._next_queued_task()

    assert claimed and claimed["id"] == "queued-compatible"
    assert db.scalar("SELECT status FROM task_runs WHERE id = ?", ["queued-compatible"]) == "running"


def test_queue_worker_logs_claim_failure_without_spinning(tmp_path, monkeypatch, caplog):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    service._write_task(
        "queued-failing-claim",
        kind="update",
        status="queued",
        stage="准备更新",
        source="本地仓库",
        summary={},
        payload={"mode": "daily_light"},
    )
    rekicks = []

    def fail_claim():
        raise RuntimeError("claim failed")

    monkeypatch.setattr(service, "_next_queued_task", fail_claim)
    monkeypatch.setattr(service, "_ensure_queue_worker", lambda: rekicks.append("rekick"))
    service._queue_worker_active = True

    with caplog.at_level(logging.ERROR):
        service._drain_queue()

    assert service._queue_worker_active is False
    assert rekicks == []
    assert "任务队列 worker 异常" in caplog.text
    assert "claim failed" in caplog.text












def test_recover_interrupted_tasks_syncs_result_tables(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    now = datetime.utcnow()
    service._write_task("ai-task", kind="candidate_ai_summary", status="running", stage="生成候选解释", source="LLM", summary={}, payload={})
    db.upsert(
        "candidate_ai_summaries",
        [
            {
                "run_id": "run-1",
                "code": "000001.SZ",
                "summary_json": None,
                "llm_model": "model-a",
                "generated_at": None,
                "status": "running",
                "task_id": "ai-task",
                "input_hash": "hash-1",
                "prompt_version": "candidate-ai-v2",
                "updated_at": now,
            }
        ],
        ["run_id", "code"],
    )
    db.upsert(
        "backtest_runs",
        [
            {
                "id": "backtest-run",
                "status": "running",
                "started_at": now,
                "finished_at": None,
                "config_json": "{}",
                "summary_json": "{}",
                "error_message": None,
            }
        ],
        ["id"],
    )
    db.upsert(
        "portfolio_backtest_runs",
        [
            {
                "id": "portfolio-run",
                "status": "running",
                "started_at": now,
                "finished_at": None,
                "config_json": "{}",
                "summary_json": "{}",
                "error_message": None,
            }
        ],
        ["id"],
    )

    service.recover_interrupted_tasks()

    assert db.scalar("SELECT status FROM task_runs WHERE id = 'ai-task'") == "failed"
    assert db.scalar("SELECT status FROM candidate_ai_summaries WHERE run_id = 'run-1' AND code = '000001.SZ'") == "failed"
    assert db.scalar("SELECT status FROM backtest_runs WHERE id = 'backtest-run'") == "failed"
    assert db.scalar("SELECT status FROM portfolio_backtest_runs WHERE id = 'portfolio-run'") == "failed"
