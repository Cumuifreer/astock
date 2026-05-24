import json
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.daily_brief_scheduler import DailyBriefScheduler
from backend.app.services.daily_brief_service import DailyBriefService
from backend.app.services.update_service import UpdateService


def test_daily_brief_service_normalizes_deepseek_model_alias(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = DailyBriefService(db, api_key="", model="v4-flash")

    assert service.model == "deepseek-v4-flash"


def test_daily_brief_service_generates_fallback_report_from_articles(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = DailyBriefService(
        db,
        sources=[{"id": "mock", "name": "Mock Feed", "type": "rss", "category": "tech", "enabled": True}],
        api_key="",
    )

    monkeypatch.setattr(
        service,
        "_fetch_source",
        lambda source: [
            {
                "source_id": "mock",
                "source": "Mock Feed",
                "category": "tech",
                "title": "Open model release changes developer tooling",
                "url": "https://example.com/open-model",
                "excerpt": "A new open model release improves local developer tooling.",
                "published_at": datetime(2026, 5, 23, 8, 0),
            }
        ],
    )
    summary = service.generate(report_date=datetime(2026, 5, 23).date())
    latest = service.latest()

    assert summary["article_count"] == 1
    assert summary["status"] == "completed_partial"
    assert latest is not None
    assert latest["hero_headline"]
    assert latest["tech_briefs"][0]["url"] == "https://example.com/open-model"
    assert "科技资讯" in latest["tech_briefs"][0]["title"]
    assert "来自 Mock Feed" in latest["tech_briefs"][0]["summary"]
    assert db.scalar("SELECT COUNT(*) FROM news_articles") == 1


def test_daily_brief_service_condenses_source_failures_for_ui(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = DailyBriefService(
        db,
        sources=[
            {"id": "mock-a", "name": "Mock A", "type": "rss", "category": "tech", "enabled": True},
            {"id": "mock-b", "name": "Mock B", "type": "rss", "category": "finance", "enabled": True},
        ],
        api_key="",
    )

    def fail_source(source):
        raise OSError("Network is unreachable")

    monkeypatch.setattr(service, "_fetch_source", fail_source)
    service.generate(report_date=datetime(2026, 5, 23).date())
    latest = service.latest()

    assert latest is not None
    assert "2 个资讯源暂不可用" in latest["error_message"]
    assert "Network is unreachable" not in latest["error_message"]
    assert "Network is unreachable" in latest["payload"]["warnings"][0]


def test_daily_brief_service_accepts_textual_importance_from_llm(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = DailyBriefService(
        db,
        sources=[{"id": "mock", "name": "Mock Feed", "type": "rss", "category": "tech", "enabled": True}],
        api_key="configured",
    )

    monkeypatch.setattr(
        service,
        "_fetch_source",
        lambda source: [
            {
                "source_id": "mock",
                "source": "Mock Feed",
                "category": "tech",
                "title": "AI agents enter developer workflow",
                "url": "https://example.com/agent-workflow",
                "excerpt": "Developer tools are adding AI agents.",
                "published_at": datetime(2026, 5, 24, 8, 0),
            }
        ],
    )
    monkeypatch.setattr(
        service,
        "_post_llm",
        lambda client, payload: {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "hero_headline": "AI 工具继续进入开发流程",
                                "daily_overview": "多家技术来源显示，AI agent 正在进入开发者工具链。",
                                "tech_briefs": [
                                    {
                                        "title": "AI agent 进入开发流程",
                                        "url": "https://example.com/agent-workflow",
                                        "source": "Mock Feed",
                                        "summary": "开发者工具继续加入 agent 能力。",
                                        "importance": "high",
                                    }
                                ],
                                "finance_briefs": [],
                                "politics_briefs": [],
                                "editor_note": "关注工具链变化。",
                                "keywords": ["AI", "开发工具"],
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        },
    )

    summary = service.generate(report_date=datetime(2026, 5, 24).date())
    latest = service.latest()

    assert summary["llm_used"] is True
    assert latest["llm_model"] == "deepseek-v4-flash"
    assert latest["tech_briefs"][0]["importance"] == 8


def test_update_service_retries_fallback_brief_after_llm_is_configured(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "daily_briefs",
        [
            {
                "id": "brief-20260523",
                "brief_date": datetime(2026, 5, 23).date(),
                "status": "completed_partial",
                "hero_headline": "fallback",
                "daily_overview": "fallback",
                "tech_briefs_json": [],
                "finance_briefs_json": [],
                "politics_briefs_json": [],
                "editor_note": "",
                "keywords_json": [],
                "article_count": 1,
                "source_count": 1,
                "llm_model": "fallback",
                "generated_at": datetime(2026, 5, 23, 8, 0),
                "error_message": "未配置 LLM API",
                "payload_json": {},
            }
        ],
        ["id"],
    )
    service = UpdateService(db)
    service.daily_brief_service.api_key = "configured"

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())
    task_id = service.ensure_daily_brief()

    assert task_id is not None
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'brief'") == 1


def test_update_service_retries_legacy_llm_400_fallback_once(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "daily_briefs",
        [
            {
                "id": "brief-20260524",
                "brief_date": datetime(2026, 5, 24).date(),
                "status": "completed_partial",
                "hero_headline": "fallback",
                "daily_overview": "fallback",
                "tech_briefs_json": [],
                "finance_briefs_json": [],
                "politics_briefs_json": [],
                "editor_note": "",
                "keywords_json": [],
                "article_count": 88,
                "source_count": 7,
                "llm_model": "fallback",
                "generated_at": datetime(2026, 5, 24, 4, 18),
                "error_message": "14 个资讯源暂不可用；LLM 简报降级：Client error '400 Bad Request' for url",
                "payload_json": {},
            }
        ],
        ["id"],
    )
    service = UpdateService(db)
    service.daily_brief_service.api_key = "configured"

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())
    task_id = service.ensure_daily_brief()

    assert task_id is not None


def test_update_service_does_not_loop_on_current_llm_400_fallback(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "daily_briefs",
        [
            {
                "id": "brief-20260524",
                "brief_date": datetime(2026, 5, 24).date(),
                "status": "completed_partial",
                "hero_headline": "fallback",
                "daily_overview": "fallback",
                "tech_briefs_json": [],
                "finance_briefs_json": [],
                "politics_briefs_json": [],
                "editor_note": "",
                "keywords_json": [],
                "article_count": 88,
                "source_count": 7,
                "llm_model": "fallback",
                "generated_at": datetime(2026, 5, 24, 4, 20),
                "error_message": "14 个资讯源暂不可用；LLM 简报降级：400 Bad Request: bad model",
                "payload_json": {},
            }
        ],
        ["id"],
    )
    service = UpdateService(db)
    service.daily_brief_service.api_key = "configured"

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())
    task_id = service.ensure_daily_brief()

    assert task_id is None


def test_update_service_enqueues_brief_when_empty(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())

    task_id = service.ensure_daily_brief()
    duplicate = service.ensure_daily_brief()

    assert task_id is not None
    assert duplicate == task_id
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'brief'") == 1


def test_daily_brief_scheduler_enqueues_daily_slot_once(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())
    scheduler = DailyBriefScheduler(service, poll_seconds=1, schedule_time="08:20")
    now = datetime(2026, 5, 23, 8, 25, tzinfo=ZoneInfo("Asia/Shanghai"))

    task_id = scheduler.tick(now)
    duplicate = scheduler.tick(now)

    row = db.query("SELECT id, status, payload_json FROM task_runs WHERE kind = 'brief'")[0]
    assert task_id == "brief-auto-20260523"
    assert duplicate is None
    assert row["status"] == "queued"
    assert '"scheduled": true' in row["payload_json"]
