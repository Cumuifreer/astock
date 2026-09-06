from datetime import datetime
from zoneinfo import ZoneInfo

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.daily_update_scheduler import DailyUpdateScheduler
from backend.app.services.data_service import DataService
from backend.app.services.update_service import UpdateService


def test_daily_update_scheduler_enqueues_daily_light_once(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())
    scheduler = DailyUpdateScheduler(service, poll_seconds=1, schedule_time="17:10")
    now = datetime(2026, 5, 22, 17, 12, tzinfo=ZoneInfo("Asia/Shanghai"))

    task_id = scheduler.tick(now)
    duplicate = scheduler.tick(now)

    rows = db.query("SELECT id, kind, status, payload_json, summary_json FROM task_runs WHERE kind = 'update'")
    assert task_id == "update-auto-20260522-1710"
    assert duplicate is None
    assert len(rows) == 1
    assert rows[0]["kind"] == "update"
    assert rows[0]["status"] == "queued"
    assert '"mode": "daily_light"' in rows[0]["payload_json"]
    assert '"scheduled": true' in rows[0]["payload_json"]
    assert '"schedule_key": "2026-05-22 17:10"' in rows[0]["payload_json"]
    assert '"scheduled": true' in rows[0]["summary_json"]


def test_review_overview_reports_daily_update_schedule(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from backend.app.services import data_service
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    monkeypatch.setattr(data_service, "settings", SimpleNamespace(daily_update_scheduler_enabled=True, daily_update_schedule_time="18:30"))
    overview = DataService(db).review_overview()
    assert overview["schedule_enabled"] is True
    assert overview["schedule_time"] == "18:30"
    assert overview["trade_date"] is None
