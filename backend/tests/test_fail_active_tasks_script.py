from backend.app.db import Database
from backend.app.schema import migrate
from scripts.fail_active_tasks import fail_active_tasks


def test_fail_active_tasks_marks_queue_and_related_runs_failed(tmp_path):
    path = tmp_path / "ashare_test.duckdb"
    db = Database(path)
    migrate(db)
    db.execute(
        """
        INSERT INTO task_runs (id, kind, status, stage, started_at, updated_at)
        VALUES ('task-running', 'update', 'running', '更新中', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
               ('task-queued', 'brief', 'queued', '等待中', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        write=True,
    )
    db.execute(
        """
        INSERT INTO analysis_runs (id, task_id, status, started_at)
        VALUES ('analysis-1', 'task-running', 'running', CURRENT_TIMESTAMP)
        """,
        write=True,
    )

    counts = fail_active_tasks(path, "test cleanup")

    assert counts["task_runs"] == 2
    assert counts["analysis_runs"] == 1
    assert db.scalar("SELECT COUNT(*) FROM task_runs WHERE status = 'failed'") == 2
    assert db.scalar("SELECT error_message FROM task_runs WHERE id = 'task-running'") == "test cleanup"
    assert db.scalar("SELECT status FROM analysis_runs WHERE id = 'analysis-1'") == "failed"
