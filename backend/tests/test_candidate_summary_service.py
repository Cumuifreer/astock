import json
from datetime import datetime

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.candidate_summary_service import CandidateSummaryService


def test_candidate_summary_returns_rule_fallback_without_api_key(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = CandidateSummaryService(db, api_key="")

    identity = service.prepare_summary_identity(
        run_id="run-1",
        code="000001.SZ",
        candidate={"code": "000001.SZ", "name": "平安银行", "reasons": ["RPS 强", "量能确认"], "metrics": {}},
        matched_rules=[],
        risk_items=[],
    )
    result = service.generate_and_store(identity)
    summary = result["summary"]

    assert summary["enabled"] is False
    assert summary["fallback_reason"] == "missing_api_key"
    assert summary["summary"].startswith("平安银行")
    assert summary["opportunities"] == ["RPS 强", "量能确认"]
    assert summary["prompt_version"]


def test_candidate_summary_sync_entrypoint_is_disabled(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = CandidateSummaryService(db, api_key="")

    try:
        service.summarize("run-1", "000001.SZ", {"code": "000001.SZ", "name": "平安银行"}, [], [])
    except RuntimeError as exc:
        assert "异步任务" in str(exc)
    else:
        raise AssertionError("synchronous candidate summary entrypoint must stay disabled")


def test_candidate_summary_status_uses_input_hash_and_prompt_version(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = CandidateSummaryService(db, api_key="configured", model="model-a")

    first = service.prepare_summary_identity(
        run_id="run-1",
        code="000001.SZ",
        candidate={"code": "000001.SZ", "name": "平安银行", "reasons": ["RPS 强"], "metrics": {"volume_ratio": 1.8}},
        matched_rules=[{"indicator_id": "rps20", "matched": True}],
        risk_items=[],
    )
    second = service.prepare_summary_identity(
        run_id="run-1",
        code="000001.SZ",
        candidate={"code": "000001.SZ", "name": "平安银行", "reasons": ["RPS 强"], "metrics": {"volume_ratio": 2.2}},
        matched_rules=[{"indicator_id": "rps20", "matched": True}],
        risk_items=[],
    )

    assert first["input_hash"] != second["input_hash"]
    assert first["prompt_version"]


def test_candidate_summary_persists_fallback_result(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = CandidateSummaryService(db, api_key="")

    identity = service.prepare_summary_identity(
        run_id="run-1",
        code="000001.SZ",
        candidate={"code": "000001.SZ", "name": "平安银行", "reasons": ["量能确认"], "metrics": {}},
        matched_rules=[],
        risk_items=[],
    )
    result = service.generate_and_store(identity, task_id="ai-summary-test")
    cached = service.read_summary("run-1", "000001.SZ", input_hash=identity["input_hash"])

    assert result["status"] == "completed_partial"
    assert result["summary"]["fallback_reason"] == "missing_api_key"
    assert cached["status"] == "completed_partial"
    assert cached["task_id"] == "ai-summary-test"


def test_candidate_summary_reads_llm_result_from_worker_store(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = CandidateSummaryService(db, api_key="configured")
    calls = {"count": 0}

    def fake_call(candidate, matched_rules, risk_items):
        calls["count"] += 1
        return {
            "summary": f"{candidate['name']} 自然语言解释",
            "opportunities": ["机会"],
            "risks": ["风险"],
            "watch_plan": ["观察"],
        }

    monkeypatch.setattr(service, "_call_llm", fake_call)

    identity = service.prepare_summary_identity(
        run_id="run-1",
        code="000001.SZ",
        candidate={"code": "000001.SZ", "name": "平安银行"},
        matched_rules=[],
        risk_items=[],
    )
    first = service.generate_and_store(identity)
    second = service.read_summary("run-1", "000001.SZ", input_hash=identity["input_hash"])

    assert first["summary"]["enabled"] is True
    assert second["summary"]["summary"] == "平安银行 自然语言解释"
    assert second["summary"]["prompt_version"] == first["summary"]["prompt_version"]
    assert calls["count"] == 1


def test_candidate_summary_ignores_old_prompt_cache(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "candidate_ai_summaries",
        [
            {
                "run_id": "run-1",
                "code": "000001.SZ",
                "summary_json": '{"enabled": true, "summary": "旧缓存"}',
                "llm_model": "old",
                "generated_at": "2026-05-28T10:00:00",
            }
        ],
        ["run_id", "code"],
    )
    service = CandidateSummaryService(db, api_key="configured")

    result = service.read_summary("run-1", "000001.SZ", input_hash="expected-new-hash")

    assert result["status"] == "stale"
    assert result["summary"]["summary"] == "旧缓存"


def test_candidate_summary_reports_llm_error_fallback(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = CandidateSummaryService(db, api_key="configured")

    def fail_call(candidate, matched_rules, risk_items):
        raise RuntimeError("401 unauthorized")

    monkeypatch.setattr(service, "_call_llm", fail_call)

    identity = service.prepare_summary_identity(
        run_id="run-1",
        code="000001.SZ",
        candidate={"code": "000001.SZ", "name": "平安银行"},
        matched_rules=[],
        risk_items=[],
    )
    result = service.generate_and_store(identity)["summary"]

    assert result["enabled"] is False
    assert result["fallback_reason"] == "llm_error"
    assert "401 unauthorized" in result["error_message"]
    assert result["summary"].startswith("平安银行")


def test_candidate_summary_reports_invalid_response_fallback(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = CandidateSummaryService(db, api_key="configured")

    def invalid_call(candidate, matched_rules, risk_items):
        raise ValueError("bad json")

    monkeypatch.setattr(service, "_call_llm", invalid_call)

    identity = service.prepare_summary_identity(
        run_id="run-1",
        code="000001.SZ",
        candidate={"code": "000001.SZ", "name": "平安银行"},
        matched_rules=[],
        risk_items=[],
    )
    result = service.generate_and_store(identity)["summary"]

    assert result["enabled"] is False
    assert result["fallback_reason"] == "invalid_response"
    assert "bad json" in result["error_message"]
    assert result["summary"].startswith("平安银行")


def test_candidate_summary_read_is_read_only(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = CandidateSummaryService(db, api_key="configured")

    def fail_call(*_args, **_kwargs):
        raise AssertionError("GET/read must not call LLM")

    monkeypatch.setattr(service, "_call_llm", fail_call)

    result = service.read_summary("run-1", "000001.SZ")

    assert result["status"] == "not_requested"
    assert result["summary"] is None


def test_candidate_summary_prepares_authoritative_evidence_from_candidate_results(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    now = datetime.utcnow()
    db.upsert(
        "candidate_results",
        [
            {
                "run_id": "run-1",
                "rank": 1,
                "code": "000001.SZ",
                "name": "平安银行",
                "signal_score": 88.0,
                "signal_type": "breakout",
                "latest_price": 12.3,
                "pct_chg": 2.1,
                "amount": 120000000.0,
                "turnover_rate": 3.2,
                "float_market_value": 5000000000.0,
                "data_sources": "{}",
                "reasons_json": json.dumps(["RPS 强", "量能确认"], ensure_ascii=False),
                "metrics_json": json.dumps(
                    {
                        "volume_ratio": 1.8,
                        "matched_rules": [{"indicator_id": "rps20", "matched": True}],
                        "risk_items": [{"indicator_id": "turnover", "reason": "换手偏高"}],
                    },
                    ensure_ascii=False,
                ),
                "created_at": now,
            }
        ],
        ["run_id", "code"],
    )
    service = CandidateSummaryService(db, api_key="")

    identity = service.prepare_from_result(run_id="run-1", code="000001.SZ")

    assert identity["candidate"]["name"] == "平安银行"
    assert identity["candidate"]["reasons"] == ["RPS 强", "量能确认"]
    assert identity["candidate"]["metrics"]["volume_ratio"] == 1.8
    assert identity["matched_rules"] == [{"indicator_id": "rps20", "matched": True}]
    assert identity["risk_items"] == [{"indicator_id": "turnover", "reason": "换手偏高"}]


def test_candidate_summary_persist_rejects_stale_task_owner(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = CandidateSummaryService(db, api_key="")
    identity = service.prepare_summary_identity(
        run_id="run-1",
        code="000001.SZ",
        candidate={"code": "000001.SZ", "name": "平安银行"},
        matched_rules=[],
        risk_items=[],
    )

    owner_cases = [
        {"task_id": "new-task", "input_hash": identity["input_hash"]},
        {"task_id": "old-task", "input_hash": "new-input-hash"},
    ]
    for owner in owner_cases:
        db.upsert(
            "candidate_ai_summaries",
            [
                {
                    "run_id": "run-1",
                    "code": "000001.SZ",
                    "status": "running",
                    "task_id": owner["task_id"],
                    "input_hash": owner["input_hash"],
                    "prompt_version": identity["prompt_version"],
                    "summary_json": None,
                    "llm_model": "model-a",
                    "generated_at": None,
                    "updated_at": datetime.utcnow(),
                }
            ],
            ["run_id", "code"],
        )

        try:
            service.persist_summary(
                identity,
                {"summary": "旧任务结果", "generated_at": datetime.utcnow().isoformat(timespec="seconds")},
                status="completed_partial",
                task_id="old-task",
            )
        except RuntimeError as exc:
            assert "任务归属" in str(exc)
        else:
            raise AssertionError("stale task owner must not overwrite candidate summary")

        row = db.query("SELECT status, task_id, input_hash, summary_json FROM candidate_ai_summaries WHERE run_id = ? AND code = ?", ["run-1", "000001.SZ"])[0]
        assert row["status"] == "running"
        assert row["task_id"] == owner["task_id"]
        assert row["input_hash"] == owner["input_hash"]
        assert row["summary_json"] is None
