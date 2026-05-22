from datetime import datetime
from zoneinfo import ZoneInfo

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.data_service import DataService
from backend.app.services.intraday_scheduler import IntradayScheduler
from backend.app.services.update_service import UpdateService


def test_intraday_scheduler_enqueues_due_beijing_slot_once(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    started = []

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            started.append(args[0].__name__)
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())
    scheduler = IntradayScheduler(service, poll_seconds=1, catchup_minutes=8)
    now = datetime(2026, 5, 22, 14, 56, tzinfo=ZoneInfo("Asia/Shanghai"))

    task_id = scheduler.tick(now)
    duplicate = scheduler.tick(now)

    rows = db.query("SELECT id, status, payload_json FROM task_runs WHERE kind = 'intraday'")
    assert task_id == "intraday-auto-20260522-1455"
    assert duplicate is None
    assert len(rows) == 1
    assert rows[0]["status"] == "queued"
    assert '"sample_at": "2026-05-22T14:55:00"' in rows[0]["payload_json"]
    assert '"schedule_key": "2026-05-22 14:55"' in rows[0]["payload_json"]


def test_intraday_scheduler_ignores_non_trading_hours(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())
    scheduler = IntradayScheduler(service, poll_seconds=1, catchup_minutes=8)

    assert scheduler.tick(datetime(2026, 5, 22, 15, 20, tzinfo=ZoneInfo("Asia/Shanghai"))) is None
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE kind = 'intraday'") == 0


def test_runtime_health_reports_scheduler_slots_and_data_dates(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    class NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service, "executor", NoopExecutor())
    scheduler = IntradayScheduler(service, poll_seconds=30, catchup_minutes=8)
    now = datetime(2026, 5, 22, 14, 56, tzinfo=ZoneInfo("Asia/Shanghai"))
    scheduler.tick(now)

    health = DataService(db).runtime_health(
        now=now,
        scheduler_enabled=True,
        poll_seconds=30,
        catchup_minutes=8,
    )
    slot_1455 = next(slot for slot in health["scheduler"]["slots"] if slot["time"] == "14:55")

    assert health["scheduler"]["enabled"] is True
    assert health["scheduler"]["timezone"] == "Asia/Shanghai"
    assert health["scheduler"]["is_weekend"] is False
    assert slot_1455["status"] == "queued"
    assert slot_1455["task_id"] == "intraday-auto-20260522-1455"
    assert health["tasks"]["queued"] == 1
    assert health["data"]["latest_history_date"] is None
