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


def test_analysis_task_auto_enqueues_candidate_ai_summaries_after_run(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    class AnalysisRunner:
        def run(self, config, progress=None, run_id=None, task_id=None):
            assert task_id == "analyze-test"
            run_id = run_id or "run-1"
            db.upsert(
                "candidate_results",
                [
                    {
                        "run_id": run_id,
                        "rank": 1,
                        "code": "000001.SZ",
                        "name": "平安银行",
                        "signal_score": 88,
                        "reasons_json": json.dumps(["放量突破"], ensure_ascii=False),
                        "metrics_json": json.dumps({"strategy_rule_results": [{"indicator_name": "量能", "matched": True}]}, ensure_ascii=False),
                        "created_at": datetime.utcnow(),
                    },
                    {
                        "run_id": run_id,
                        "rank": 2,
                        "code": "000002.SZ",
                        "name": "万科A",
                        "signal_score": 82,
                        "reasons_json": json.dumps(["趋势延续"], ensure_ascii=False),
                        "metrics_json": json.dumps({"strategy_rule_results": [{"indicator_name": "趋势", "matched": True}]}, ensure_ascii=False),
                        "created_at": datetime.utcnow(),
                    },
                ],
                ["run_id", "code"],
            )
            return run_id

    class CandidateSummaryRunner:
        def prepare_from_result(self, run_id, code, require_existing=False):
            assert require_existing is True
            return {
                "run_id": run_id,
                "code": code,
                "input_hash": f"hash-{code}",
                "prompt_version": "candidate-ai-v2",
                "llm_model": "model-a",
                "evidence": {"candidate": {"code": code}},
            }

        def read_summary(self, run_id, code, input_hash=None):
            return {"status": "not_requested", "run_id": run_id, "code": code, "summary": None}

        def mark_queued(self, identity, task_id):
            db.upsert(
                "candidate_ai_summaries",
                [
                    {
                        "run_id": identity["run_id"],
                        "code": identity["code"],
                        "summary_json": None,
                        "llm_model": identity["llm_model"],
                        "generated_at": None,
                        "status": "queued",
                        "task_id": task_id,
                        "input_hash": identity["input_hash"],
                        "prompt_version": identity["prompt_version"],
                        "evidence_json": json.dumps(identity["evidence"], ensure_ascii=False),
                    }
                ],
                ["run_id", "code"],
            )

    monkeypatch.setattr(service, "executor", NoopExecutor())
    service.candidate_summary_runner = CandidateSummaryRunner()
    service._write_task(
        "analyze-test",
        kind="analyze",
        status="running",
        stage="准备分析",
        source="本地仓库",
        summary={},
        payload={},
    )

    service._run_analysis("analyze-test", {}, AnalysisRunner(), run_id="run-1")

    tasks = db.query("SELECT kind, status, payload_json FROM task_runs WHERE kind = 'candidate_ai_summary' ORDER BY payload_json")
    summaries = db.query("SELECT code, status FROM candidate_ai_summaries ORDER BY code")
    assert len(tasks) == 2
    assert {json.loads(row["payload_json"])["code"] for row in tasks} == {"000001.SZ", "000002.SZ"}
    assert {row["status"] for row in tasks} == {"queued"}
    assert summaries == [{"code": "000001.SZ", "status": "queued"}, {"code": "000002.SZ", "status": "queued"}]


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


def test_candidate_ai_summary_task_enqueues_and_marks_result_queued(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    class Runner:
        def prepare_from_result(self, run_id, code, require_existing=False):
            assert require_existing is True
            return {
                "run_id": run_id,
                "code": code,
                "input_hash": "hash-1",
                "prompt_version": "candidate-ai-v2",
                "llm_model": "model-a",
                "evidence": {"candidate": {"code": code}},
            }

        def read_summary(self, run_id, code, input_hash=None):
            return {"status": "not_requested", "run_id": run_id, "code": code, "summary": None}

        def mark_queued(self, identity, task_id):
            db.upsert(
                "candidate_ai_summaries",
                [
                    {
                        "run_id": identity["run_id"],
                        "code": identity["code"],
                        "summary_json": None,
                        "llm_model": identity["llm_model"],
                        "generated_at": None,
                        "status": "queued",
                        "task_id": task_id,
                        "input_hash": identity["input_hash"],
                        "prompt_version": identity["prompt_version"],
                        "evidence_json": json.dumps(identity["evidence"], ensure_ascii=False),
                    }
                ],
                ["run_id", "code"],
            )

    monkeypatch.setattr(service, "executor", NoopExecutor())

    task_id, identity = service.start_candidate_ai_summary(
        {"run_id": "run-1", "code": "000001.SZ", "force": False},
        Runner(),
    )

    task = db.query("SELECT id, kind, status, payload_json FROM task_runs WHERE id = ?", [task_id])[0]
    row = db.query("SELECT status, task_id, input_hash FROM candidate_ai_summaries WHERE run_id = ? AND code = ?", ["run-1", "000001.SZ"])[0]
    assert task_id.startswith("ai-summary-")
    assert identity["input_hash"] == "hash-1"
    assert task["kind"] == "candidate_ai_summary"
    assert task["status"] == "queued"
    assert '"input_hash": "hash-1"' in task["payload_json"]
    assert row == {"status": "queued", "task_id": task_id, "input_hash": "hash-1"}


def test_core_task_starters_reuse_active_matching_payloads(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())

    update_first = service.start_update({"mode": "daily_light"})
    update_second = service.start_update({"mode": "daily_light"})
    analyze_first = service.start_analysis({"candidate_limit": 5}, AnalysisService(db))
    analyze_second = service.start_analysis({"candidate_limit": 5}, AnalysisService(db))
    backtest_first = service.start_backtest({"config": {"candidate_limit": 3}}, object())
    backtest_second = service.start_backtest({"config": {"candidate_limit": 3}}, object())

    assert update_second == update_first
    assert analyze_second == analyze_first
    assert backtest_second == backtest_first
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'update'") == 1
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'analyze'") == 1
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'backtest'") == 1


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
    backtest_id, backtest_run = service.start_backtest({"config": {"candidate_limit": 3}}, object())

    rows = db.query("SELECT id, payload_hash FROM task_runs ORDER BY id")
    hashes = {row["id"]: row["payload_hash"] for row in rows}

    assert hashes[update_id]
    assert hashes[analyze_id]
    assert hashes[backtest_id]
    assert service.start_analysis({"candidate_limit": 5}, AnalysisService(db)) == (analyze_id, analyze_run)
    assert service.start_backtest({"config": {"candidate_limit": 3}}, object()) == (backtest_id, backtest_run)


def test_heavy_queue_task_fails_before_runner_when_memory_is_low(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class Runner:
        def run(self, *args, **kwargs):
            raise AssertionError("analysis runner should not start under low memory")

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
    assert row["status"] == "failed"
    assert row["stage"] == "任务失败"
    assert "可用内存不足" in row["warning"]
    assert "可用内存不足" in row["error_message"]


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


def test_candidate_ai_summary_task_rejects_missing_candidate(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class Runner:
        def prepare_from_result(self, run_id, code, require_existing=False):
            assert require_existing is True
            raise ValueError("候选不存在，无法生成解释。")

    try:
        service.start_candidate_ai_summary({"run_id": "missing-run", "code": "000001.SZ"}, Runner())
    except ValueError as exc:
        assert "候选不存在" in str(exc)
    else:
        raise AssertionError("missing candidate should not enqueue a task")

    assert db.scalar("SELECT COUNT(*) FROM task_runs") == 0
    assert db.scalar("SELECT COUNT(*) FROM candidate_ai_summaries") == 0


def test_candidate_ai_summary_orphan_running_result_can_reenqueue(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    class Runner:
        def prepare_from_result(self, run_id, code, require_existing=False):
            return {
                "run_id": run_id,
                "code": code,
                "input_hash": "hash-1",
                "prompt_version": "candidate-ai-v2",
                "llm_model": "model-a",
                "evidence": {"candidate": {"code": code}},
            }

        def read_summary(self, run_id, code, input_hash=None):
            return {"status": "running", "run_id": run_id, "code": code, "task_id": "missing-task", "summary": None}

        def mark_queued(self, identity, task_id):
            db.upsert(
                "candidate_ai_summaries",
                [
                    {
                        "run_id": identity["run_id"],
                        "code": identity["code"],
                        "summary_json": None,
                        "llm_model": identity["llm_model"],
                        "generated_at": None,
                        "status": "queued",
                        "task_id": task_id,
                        "input_hash": identity["input_hash"],
                        "prompt_version": identity["prompt_version"],
                        "evidence_json": json.dumps(identity["evidence"], ensure_ascii=False),
                    }
                ],
                ["run_id", "code"],
            )

    monkeypatch.setattr(service, "executor", NoopExecutor())

    task_id, identity = service.start_candidate_ai_summary(
        {"run_id": "run-1", "code": "000001.SZ"},
        Runner(),
    )

    assert task_id.startswith("ai-summary-")
    assert task_id != "missing-task"
    assert identity["status"] == "queued"
    assert db.scalar("SELECT status FROM task_runs WHERE id = ?", [task_id]) == "queued"


def test_candidate_ai_summary_force_reuses_active_owner(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    class Runner:
        def prepare_from_result(self, run_id, code, require_existing=False):
            return {
                "run_id": run_id,
                "code": code,
                "input_hash": "hash-1",
                "prompt_version": "candidate-ai-v2",
                "llm_model": "model-a",
                "evidence": {"candidate": {"code": code}},
            }

        def read_summary(self, run_id, code, input_hash=None):
            return {
                "status": "running",
                "run_id": run_id,
                "code": code,
                "task_id": "ai-existing",
                "input_hash": input_hash,
                "summary": None,
            }

        def mark_queued(self, *_args, **_kwargs):
            raise AssertionError("force must not overwrite an active candidate summary owner")

    monkeypatch.setattr(service, "executor", NoopExecutor())
    service._write_task(
        "ai-existing",
        kind="candidate_ai_summary",
        status="running",
        stage="生成候选解释",
        source="LLM",
        summary={},
        payload={"run_id": "run-1", "code": "000001.SZ", "input_hash": "hash-1"},
    )

    task_id, identity = service.start_candidate_ai_summary(
        {"run_id": "run-1", "code": "000001.SZ", "force": True},
        Runner(),
    )

    assert task_id == "ai-existing"
    assert identity["status"] == "running"
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'candidate_ai_summary'") == 1


def test_candidate_ai_summary_dispatch_persists_result_and_completes_task(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    task_id = "ai-summary-test"
    identity = {
        "run_id": "run-1",
        "code": "000001.SZ",
        "input_hash": "hash-1",
        "prompt_version": "candidate-ai-v2",
        "llm_model": "model-a",
        "evidence": {"candidate": {"code": "000001.SZ"}},
    }

    class Runner:
        def prepare_from_result(self, run_id, code, require_existing=False):
            assert require_existing is True
            assert (run_id, code) == ("run-1", "000001.SZ")
            return identity

        def mark_running(self, identity, task_id):
            db.upsert(
                "candidate_ai_summaries",
                [
                    {
                        "run_id": identity["run_id"],
                        "code": identity["code"],
                        "summary_json": None,
                        "llm_model": identity["llm_model"],
                        "generated_at": None,
                        "status": "running",
                        "task_id": task_id,
                        "input_hash": identity["input_hash"],
                        "prompt_version": identity["prompt_version"],
                    }
                ],
                ["run_id", "code"],
            )

        def generate_and_store(self, identity, task_id):
            db.upsert(
                "candidate_ai_summaries",
                [
                    {
                        "run_id": identity["run_id"],
                        "code": identity["code"],
                        "summary_json": json.dumps({"summary": "规则解释", "fallback_reason": "missing_api_key"}, ensure_ascii=False),
                        "llm_model": identity["llm_model"],
                        "generated_at": datetime.utcnow(),
                        "status": "completed_partial",
                        "task_id": task_id,
                        "input_hash": identity["input_hash"],
                        "prompt_version": identity["prompt_version"],
                    }
                ],
                ["run_id", "code"],
            )
            return {
                "status": "completed_partial",
                "task_id": task_id,
                "run_id": identity["run_id"],
                "code": identity["code"],
                "input_hash": identity["input_hash"],
                "summary": {"summary": "规则解释", "fallback_reason": "missing_api_key"},
            }

    service.candidate_summary_runner = Runner()
    service._write_task(
        task_id,
        kind="candidate_ai_summary",
        status="running",
        stage="准备生成候选解释",
        source="LLM",
        summary={},
        payload={"run_id": "run-1", "code": "000001.SZ", "input_hash": "hash-1"},
    )

    service._dispatch_queued_task({"id": task_id, "kind": "candidate_ai_summary"}, {"run_id": "run-1", "code": "000001.SZ", "input_hash": "hash-1"})

    task = db.query("SELECT status, stage, summary_json FROM task_runs WHERE id = ?", [task_id])[0]
    row = db.query("SELECT status, task_id FROM candidate_ai_summaries WHERE run_id = ? AND code = ?", ["run-1", "000001.SZ"])[0]
    summary = json.loads(task["summary_json"] or "{}")
    assert task["status"] == "completed_partial"
    assert task["stage"] == "候选解释完成"
    assert summary["run_id"] == "run-1"
    assert summary["code"] == "000001.SZ"
    assert row == {"status": "completed_partial", "task_id": task_id}


def test_candidate_ai_summary_dispatch_fails_when_input_hash_changed(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    task_id = "ai-summary-test"

    class Runner:
        def prepare_from_result(self, run_id, code, require_existing=False):
            assert require_existing is True
            return {
                "run_id": run_id,
                "code": code,
                "input_hash": "hash-new",
                "prompt_version": "candidate-ai-v2",
                "llm_model": "model-a",
                "evidence": {"candidate": {"code": code}},
            }

        def mark_running(self, *_args, **_kwargs):
            raise AssertionError("stale task must fail before marking result running")

        def generate_and_store(self, *_args, **_kwargs):
            raise AssertionError("stale task must not call the LLM path")

        def mark_failed(self, identity, task_id, error_message):
            db.upsert(
                "candidate_ai_summaries",
                [
                    {
                        "run_id": identity["run_id"],
                        "code": identity["code"],
                        "summary_json": None,
                        "llm_model": identity["llm_model"],
                        "generated_at": None,
                        "status": "failed",
                        "task_id": task_id,
                        "input_hash": identity["input_hash"],
                        "prompt_version": identity["prompt_version"],
                        "error_message": error_message,
                    }
                ],
                ["run_id", "code"],
            )

    service.candidate_summary_runner = Runner()
    service._write_task(
        task_id,
        kind="candidate_ai_summary",
        status="running",
        stage="准备生成候选解释",
        source="LLM",
        summary={},
        payload={"run_id": "run-1", "code": "000001.SZ", "input_hash": "hash-old"},
    )

    service._dispatch_queued_task({"id": task_id, "kind": "candidate_ai_summary"}, {"run_id": "run-1", "code": "000001.SZ", "input_hash": "hash-old"})

    task = db.query("SELECT status, error_message FROM task_runs WHERE id = ?", [task_id])[0]
    result = db.query("SELECT status, input_hash, error_message FROM candidate_ai_summaries WHERE run_id = ? AND code = ?", ["run-1", "000001.SZ"])[0]
    assert task["status"] == "failed"
    assert "输入已变化" in task["error_message"]
    assert result["status"] == "failed"
    assert result["input_hash"] == "hash-new"


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


def test_stale_running_watchdog_fails_old_tasks_and_syncs_result_tables(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())
    now = datetime(2026, 1, 1, 11, 0)
    stale_at = now - timedelta(hours=2)
    fresh_at = now - timedelta(minutes=5)

    task_payloads = {
        "update-stale": ("update", {"mode": "daily_light"}),
        "analysis-task": ("analyze", {"run_id": "analysis-stale"}),
        "backtest-task": ("backtest", {"run_id": "backtest-stale"}),
        "portfolio-task": ("backtest", {"run_id": "portfolio-stale", "backtest_mode": "portfolio"}),
        "ai-task": ("candidate_ai_summary", {"run_id": "run-1", "code": "000001.SZ", "input_hash": "hash-1"}),
    }
    for task_id, (kind, payload) in task_payloads.items():
        service._write_task(task_id, kind=kind, status="running", stage="测试", payload=payload)
        db.execute("UPDATE task_runs SET updated_at = ? WHERE id = ?", [stale_at, task_id], write=True)
    service._write_task("fresh-running", kind="update", status="running", stage="测试", payload={"mode": "fresh"})
    db.execute("UPDATE task_runs SET updated_at = ? WHERE id = ?", [fresh_at, "fresh-running"], write=True)

    db.upsert(
        "analysis_runs",
        [
            {
                "id": "analysis-stale",
                "status": "running",
                "started_at": stale_at,
                "finished_at": None,
                "config_json": "{}",
                "summary_json": "{}",
                "error_message": None,
                "task_id": "analysis-task",
            }
        ],
        ["id"],
    )
    db.upsert(
        "backtest_runs",
        [
            {
                "id": "backtest-stale",
                "status": "running",
                "started_at": stale_at,
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
                "id": "portfolio-stale",
                "status": "running",
                "started_at": stale_at,
                "finished_at": None,
                "config_json": "{}",
                "summary_json": "{}",
                "error_message": None,
            }
        ],
        ["id"],
    )
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
                "updated_at": stale_at,
            }
        ],
        ["run_id", "code"],
    )

    failed_count = service.fail_stale_running_tasks(stale_after=timedelta(minutes=30), now=now)
    restarted_update = service.start_update({"mode": "daily_light"})

    assert failed_count == len(task_payloads)
    assert db.scalar("SELECT status FROM task_runs WHERE id = 'update-stale'") == "failed"
    assert db.scalar("SELECT status FROM task_runs WHERE id = 'fresh-running'") == "running"
    assert db.scalar("SELECT status FROM analysis_runs WHERE id = 'analysis-stale'") == "failed"
    assert db.scalar("SELECT status FROM backtest_runs WHERE id = 'backtest-stale'") == "failed"
    assert db.scalar("SELECT status FROM portfolio_backtest_runs WHERE id = 'portfolio-stale'") == "failed"
    assert db.scalar("SELECT status FROM candidate_ai_summaries WHERE run_id = 'run-1' AND code = '000001.SZ'") == "failed"
    assert restarted_update != "update-stale"


def test_market_environment_update_mode_uses_fast_path_without_full_update(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    service._write_task(
        "market-env-test",
        kind="update",
        status="running",
        stage="准备更新",
        source="本地仓库",
        summary={},
        payload={"mode": "market_environment"},
    )
    seen_targets = []

    def fake_market_environment(target_date):
        seen_targets.append(target_date)
        return 1

    def fail_full_update(*_args, **_kwargs):
        raise AssertionError("market_environment mode must not enter the full update flow")

    monkeypatch.setattr(service, "_update_market_environment", fake_market_environment)
    monkeypatch.setattr(service, "_update_basics", fail_full_update)

    service._run_update("market-env-test", {"mode": "market_environment"})

    task = DataService(db).latest_task("update")
    checkpoints = DataService(db).task_checkpoints("market-env-test")
    assert seen_targets
    assert task["status"] == "completed_full"
    assert task["summary"]["mode"] == "market_environment"
    assert [row["job_id"] for row in checkpoints] == ["market_environment", "capability_refresh"]
