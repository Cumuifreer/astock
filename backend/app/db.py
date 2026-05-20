from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

import duckdb

from backend.app.config import settings


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.RLock()

    @contextmanager
    def connect(self) -> Iterator[duckdb.DuckDBPyConnection]:
        conn = duckdb.connect(str(self.path))
        try:
            yield conn
        finally:
            conn.close()

    def execute(self, sql: str, params: Optional[Sequence[Any]] = None, write: bool = False) -> None:
        params = params or []
        lock = self._write_lock if write else _NoopLock()
        with lock:
            with self.connect() as conn:
                conn.execute(sql, params)

    def query(self, sql: str, params: Optional[Sequence[Any]] = None) -> List[Dict[str, Any]]:
        params = params or []
        with self.connect() as conn:
            cur = conn.execute(sql, params)
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    def scalar(self, sql: str, params: Optional[Sequence[Any]] = None) -> Any:
        rows = self.query(sql, params)
        if not rows:
            return None
        return next(iter(rows[0].values()))

    def upsert(
        self,
        table: str,
        rows: Iterable[Dict[str, Any]],
        key_columns: Sequence[str],
    ) -> int:
        materialized = [normalize_value(row) for row in rows]
        if not materialized:
            return 0
        columns = list(materialized[0].keys())
        placeholders = ", ".join(["?"] * len(columns))
        column_sql = ", ".join(columns)
        conflict_sql = ", ".join(key_columns)
        update_columns = [column for column in columns if column not in key_columns]
        if update_columns:
            update_sql = ", ".join([f"{column} = excluded.{column}" for column in update_columns])
            insert_sql = (
                f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) "
                f"ON CONFLICT ({conflict_sql}) DO UPDATE SET {update_sql}"
            )
        else:
            insert_sql = (
                f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) "
                f"ON CONFLICT ({conflict_sql}) DO NOTHING"
            )
        with self._write_lock:
            with self.connect() as conn:
                conn.execute("BEGIN TRANSACTION")
                try:
                    for row in materialized:
                        conn.execute(insert_sql, [row[column] for column in columns])
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        return len(materialized)


class _NoopLock:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


def normalize_value(row: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (dict, list, tuple)):
            clean[key] = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, datetime):
            clean[key] = value.isoformat(timespec="seconds")
        else:
            clean[key] = value
    return clean


_database: Optional[Database] = None


def get_database() -> Database:
    global _database
    if _database is None:
        _database = Database(settings.db_path)
    return _database
