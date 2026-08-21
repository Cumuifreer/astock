from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import settings


DEFAULT_MESSAGE = "管理员在服务停止后清理卡住或积压的任务。"


def fail_active_tasks(db_path: Path, message: str = DEFAULT_MESSAGE) -> Dict[str, int]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute("BEGIN TRANSACTION")
        task_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM task_runs WHERE status IN ('queued', 'running')"
            ).fetchone()[0]
        )
        conn.execute(
            """
            UPDATE task_runs
            SET status = 'failed',
                stage = '管理员清理积压任务',
                warning = ?,
                error_message = ?,
                finished_at = ?,
                updated_at = ?
            WHERE status IN ('queued', 'running')
            """,
            [message, message, now, now],
        )
        related_counts: Dict[str, int] = {}
        for table in (
            "analysis_runs",
            "backtest_runs",
            "portfolio_backtest_runs",
            "candidate_ai_summaries",
        ):
            count = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE status IN ('queued', 'running')"
                ).fetchone()[0]
            )
            related_counts[table] = count
            if table == "candidate_ai_summaries":
                conn.execute(
                    f"""
                    UPDATE {table}
                    SET status = 'failed', error_message = ?, updated_at = ?
                    WHERE status IN ('queued', 'running')
                    """,
                    [message, now],
                )
            else:
                conn.execute(
                    f"""
                    UPDATE {table}
                    SET status = 'failed', error_message = ?, finished_at = ?
                    WHERE status IN ('queued', 'running')
                    """,
                    [message, now],
                )
        conn.execute("COMMIT")
        return {"task_runs": task_count, **related_counts}
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mark queued/running tasks failed after the application service has stopped."
    )
    parser.add_argument("--db", type=Path, default=settings.db_path)
    parser.add_argument("--message", default=DEFAULT_MESSAGE)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"database not found: {args.db}")
    counts = fail_active_tasks(args.db, args.message)
    print("failed active rows:", ", ".join(f"{key}={value}" for key, value in counts.items()))


if __name__ == "__main__":
    main()
