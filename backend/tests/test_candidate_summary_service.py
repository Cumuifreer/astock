from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.candidate_summary_service import CandidateSummaryService


def test_candidate_summary_returns_rule_fallback_without_api_key(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = CandidateSummaryService(db, api_key="")

    result = service.summarize(
        "run-1",
        "000001.SZ",
        {"code": "000001.SZ", "name": "平安银行", "reasons": ["RPS 强", "量能确认"], "metrics": {}},
        matched_rules=[],
        risk_items=[],
    )

    assert result["enabled"] is False
    assert result["fallback_reason"] == "missing_api_key"
    assert result["summary"].startswith("平安银行")
    assert result["opportunities"] == ["RPS 强", "量能确认"]
    assert result["prompt_version"]


def test_candidate_summary_caches_llm_result(tmp_path, monkeypatch):
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

    first = service.summarize("run-1", "000001.SZ", {"code": "000001.SZ", "name": "平安银行"}, [], [])
    second = service.summarize("run-1", "000001.SZ", {"code": "000001.SZ", "name": "平安银行"}, [], [])

    assert first["enabled"] is True
    assert second["summary"] == "平安银行 自然语言解释"
    assert second["prompt_version"] == first["prompt_version"]
    assert calls["count"] == 1


def test_candidate_summary_ignores_old_prompt_cache(tmp_path, monkeypatch):
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
    calls = {"count": 0}

    def fake_call(candidate, matched_rules, risk_items):
        calls["count"] += 1
        return {"summary": "新解读", "opportunities": ["新机会"], "risks": ["新风险"], "watch_plan": ["新观察"]}

    monkeypatch.setattr(service, "_call_llm", fake_call)

    result = service.summarize("run-1", "000001.SZ", {"code": "000001.SZ", "name": "平安银行"}, [], [])

    assert result["summary"] == "新解读"
    assert result["prompt_version"]
    assert calls["count"] == 1


def test_candidate_summary_reports_llm_error_fallback(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = CandidateSummaryService(db, api_key="configured")

    def fail_call(candidate, matched_rules, risk_items):
        raise RuntimeError("401 unauthorized")

    monkeypatch.setattr(service, "_call_llm", fail_call)

    result = service.summarize("run-1", "000001.SZ", {"code": "000001.SZ", "name": "平安银行"}, [], [])

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

    result = service.summarize("run-1", "000001.SZ", {"code": "000001.SZ", "name": "平安银行"}, [], [])

    assert result["enabled"] is False
    assert result["fallback_reason"] == "invalid_response"
    assert "bad json" in result["error_message"]
    assert result["summary"].startswith("平安银行")
