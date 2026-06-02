import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.daily_brief_scheduler import DailyBriefScheduler
from backend.app.services.daily_brief_service import DailyBriefService
from backend.app.services.data_service import DataService
from backend.app.services.update_service import UpdateService


def test_daily_brief_generation_is_disabled_without_fetching_sources(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = DailyBriefService(
        db,
        sources=[{"id": "mock", "name": "Mock Feed", "type": "rss", "category": "tech", "enabled": True}],
        api_key="",
    )

    monkeypatch.setattr(service, "_fetch_source", lambda source: (_ for _ in ()).throw(AssertionError("must not fetch")))

    with pytest.raises(RuntimeError, match="已禁用"):
        service.generate(report_date=datetime(2026, 5, 23).date())
    assert db.scalar("SELECT COUNT(*) FROM news_articles") == 0


def test_daily_brief_api_backfills_article_flow_for_legacy_briefs(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    generated_at = datetime(2026, 5, 24, 8, 20)
    articles = [
        {
            "source_id": "mock-tech",
            "source": "Mock Tech",
            "category": "tech",
            "title": f"AI infrastructure update {index}",
            "url": f"https://example.com/tech/{index}",
            "excerpt": f"AI infrastructure detail {index}",
            "published_at": datetime(2026, 5, 24, 8, index),
            "fetched_at": generated_at,
        }
        for index in range(8)
    ]
    articles.append(
        {
            "source_id": "github-trending",
            "source": "GitHub Trending",
            "category": "tech",
            "title": "Repository trend should be hidden",
            "url": "https://github.com/example/hidden",
            "excerpt": "GitHub Trending should no longer appear in the brief.",
            "published_at": datetime(2026, 5, 24, 8, 30),
            "fetched_at": generated_at,
        }
    )
    db.upsert("news_articles", articles, ["source_id", "url"])
    db.upsert(
        "daily_briefs",
        [
            {
                "id": "brief-20260524",
                "brief_date": datetime(2026, 5, 24).date(),
                "status": "completed_partial",
                "hero_headline": "今日资讯简报",
                "daily_overview": "",
                "tech_briefs_json": [],
                "finance_briefs_json": [],
                "politics_briefs_json": [],
                "editor_note": "",
                "keywords_json": [],
                "article_count": 8,
                "source_count": 1,
                "llm_model": "fallback",
                "generated_at": generated_at,
                "error_message": None,
                "payload_json": {
                    "article_flow": {
                        "tech": [
                            {
                                "title": "Existing translated item",
                                "url": "https://example.com/tech/0",
                                "source": "Mock Tech",
                                "category": "tech",
                                "summary": "LLM translated summary",
                                "published_at": "",
                            },
                            {
                                "title": "Cached GitHub item",
                                "url": "https://github.com/example/cached",
                                "source": "GitHub Trending",
                                "category": "tech",
                                "summary": "This cached item should be hidden.",
                                "published_at": "",
                            }
                        ],
                        "finance": [],
                        "politics": [],
                    }
                },
            }
        ],
        ["id"],
    )

    latest = DataService(db).latest_daily_brief()

    assert latest is not None
    assert len(latest["article_flow"]["tech"]) == 8
    assert latest["article_flow"]["tech"][0]["title"] == "AI infrastructure update 7"
    assert latest["article_flow"]["tech"][-1]["title"] == "Existing translated item"
    assert latest["article_flow"]["tech"][-1]["published_at"] == "2026-05-24T08:00:00"
    assert "GitHub Trending" not in json.dumps(latest, ensure_ascii=False, default=str)


def test_update_service_does_not_retry_fallback_brief_after_llm_is_configured(tmp_path, monkeypatch):
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

    assert task_id is None
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'brief'") == 0


def test_update_service_does_not_retry_legacy_llm_400_fallback(tmp_path, monkeypatch):
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

    assert task_id is None
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'brief'") == 0


def test_update_service_does_not_retry_llm_brief_without_translated_article_flow(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    db.upsert(
        "daily_briefs",
        [
            {
                "id": "brief-20260524",
                "brief_date": datetime(2026, 5, 24).date(),
                "status": "completed_partial",
                "hero_headline": "old llm",
                "daily_overview": "old llm",
                "tech_briefs_json": [],
                "finance_briefs_json": [],
                "politics_briefs_json": [],
                "editor_note": "",
                "keywords_json": [],
                "article_count": 88,
                "source_count": 7,
                "llm_model": "deepseek-v4-flash",
                "generated_at": datetime(2026, 5, 24, 6, 13),
                "error_message": None,
                "payload_json": {"llm_used": True, "article_flow": {"tech": [], "finance": [], "politics": []}},
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
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'brief'") == 0


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


def test_update_service_does_not_enqueue_brief_when_empty(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())

    task_id = service.ensure_daily_brief()
    duplicate = service.ensure_daily_brief()

    assert task_id is None
    assert duplicate is None
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'brief'") == 0


def test_legacy_brief_task_dispatch_is_disabled(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    service._write_task(
        "brief-legacy",
        kind="brief",
        status="running",
        stage="准备资讯简报",
        source=None,
        summary={},
        payload={},
    )

    def fail_generate(*_args, **_kwargs):
        raise AssertionError("brief dispatch must not fetch external sources")

    monkeypatch.setattr(service.daily_brief_service, "generate", fail_generate)

    service._run_daily_brief("brief-legacy", {})
    row = db.query("SELECT status, stage, error_message FROM task_runs WHERE id = 'brief-legacy'")[0]

    assert row["status"] == "failed"
    assert row["stage"] == "资讯简报已禁用"
    assert "已禁用" in row["error_message"]


def test_daily_brief_scheduler_does_not_enqueue_daily_slot(tmp_path, monkeypatch):
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

    assert task_id is None
    assert duplicate is None
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'brief'") == 0


def test_daily_brief_scheduler_multiple_daily_slots_stay_disabled(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())
    scheduler = DailyBriefScheduler(service, poll_seconds=1, schedule_time="08:20,18:20")

    before_first = scheduler.tick(datetime(2026, 5, 23, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
    morning = scheduler.tick(datetime(2026, 5, 23, 8, 25, tzinfo=ZoneInfo("Asia/Shanghai")))
    morning_duplicate = scheduler.tick(datetime(2026, 5, 23, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
    evening = scheduler.tick(datetime(2026, 5, 23, 18, 25, tzinfo=ZoneInfo("Asia/Shanghai")))

    task_ids = [
        row["id"]
        for row in db.query("SELECT id FROM task_runs WHERE kind = 'brief' ORDER BY id")
    ]
    assert before_first is None
    assert morning is None
    assert morning_duplicate is None
    assert evening is None
    assert task_ids == []


def test_daily_brief_scheduler_catchup_stays_disabled(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())
    scheduler = DailyBriefScheduler(service, poll_seconds=1, schedule_time="08:20,18:20")

    task_id = scheduler.tick(datetime(2026, 5, 23, 19, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert task_id is None
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'brief'") == 0
