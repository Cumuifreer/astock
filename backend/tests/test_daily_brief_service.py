from datetime import datetime
from zoneinfo import ZoneInfo

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.daily_brief_scheduler import DailyBriefScheduler
from backend.app.services.daily_brief_service import DailyBriefService
from backend.app.services.update_service import UpdateService


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
    assert db.scalar("SELECT COUNT(*) FROM news_articles") == 1


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
