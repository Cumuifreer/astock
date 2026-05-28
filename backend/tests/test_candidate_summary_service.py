from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.candidate_summary_service import CandidateSummaryService, FALLBACK_SUMMARY


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
    assert result["summary"] == FALLBACK_SUMMARY
    assert result["opportunities"] == ["RPS 强", "量能确认"]


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
    assert calls["count"] == 1
