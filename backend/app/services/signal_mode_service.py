from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.app.db import Database
from backend.app.services.indicator_registry import DEFAULT_SIGNAL_MODES, blank_signal_mode, normalize_signal_mode


SIGNAL_MODE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS signal_modes (
    id TEXT PRIMARY KEY,
    name TEXT,
    mode_json TEXT,
    sort_order INTEGER,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    deleted_at TIMESTAMP
)
"""


class SignalModeService:
    def __init__(self, db: Database):
        self.db = db

    def ensure_table(self) -> None:
        self.db.execute(SIGNAL_MODE_TABLE_SQL, write=True)

    def ensure_seeded(self) -> None:
        self.ensure_table()
        if self.db.scalar("SELECT COUNT(*) FROM signal_modes WHERE deleted_at IS NULL"):
            return
        now = datetime.utcnow()
        rows = []
        for index, mode in enumerate(DEFAULT_SIGNAL_MODES):
            normalized = normalize_signal_mode(mode)
            rows.append(
                {
                    "id": normalized["id"],
                    "name": normalized["name"],
                    "mode_json": json.dumps(normalized, ensure_ascii=False),
                    "sort_order": index,
                    "created_at": now,
                    "updated_at": now,
                    "deleted_at": None,
                }
            )
        self.db.upsert("signal_modes", rows, ["id"])

    def list_modes(self) -> List[Dict[str, Any]]:
        self.ensure_seeded()
        rows = self.db.query(
            """
            SELECT id, name, mode_json, sort_order, created_at, updated_at
            FROM signal_modes
            WHERE deleted_at IS NULL
            ORDER BY sort_order ASC, updated_at ASC, name ASC
            """
        )
        return [self._decode(row) for row in rows]

    def get_mode(self, mode_id: str) -> Optional[Dict[str, Any]]:
        self.ensure_table()
        rows = self.db.query(
            """
            SELECT id, name, mode_json, sort_order, created_at, updated_at
            FROM signal_modes
            WHERE id = ? AND deleted_at IS NULL
            LIMIT 1
            """,
            [mode_id],
        )
        if not rows:
            return None
        return self._decode(rows[0])

    def create_mode(self, name: str = "新信号模式") -> Dict[str, Any]:
        mode = blank_signal_mode(name)
        mode["id"] = f"mode-{uuid.uuid4().hex[:12]}"
        return self.save_mode(mode)

    def duplicate_mode(self, mode_id: str) -> Optional[Dict[str, Any]]:
        mode = self.get_mode(mode_id)
        if not mode:
            return None
        mode["id"] = f"mode-{uuid.uuid4().hex[:12]}"
        mode["name"] = f"{mode['name']} 副本"
        return self.save_mode(mode)

    def save_mode(self, mode: Dict[str, Any]) -> Dict[str, Any]:
        self.ensure_table()
        normalized = normalize_signal_mode(mode or {})
        mode_id = normalized.get("id") or f"mode-{uuid.uuid4().hex[:12]}"
        normalized["id"] = mode_id
        existing = self.db.query(
            """
            SELECT created_at, sort_order
            FROM signal_modes
            WHERE id = ?
            LIMIT 1
            """,
            [mode_id],
        )
        now = datetime.utcnow()
        sort_order = existing[0]["sort_order"] if existing else self._next_sort_order()
        created_at = existing[0]["created_at"] if existing else now
        self.db.upsert(
            "signal_modes",
            [
                {
                    "id": mode_id,
                    "name": normalized["name"],
                    "mode_json": json.dumps(self._json_payload(normalized), ensure_ascii=False),
                    "sort_order": sort_order,
                    "created_at": created_at,
                    "updated_at": now,
                    "deleted_at": None,
                }
            ],
            ["id"],
        )
        saved = self.get_mode(mode_id)
        if saved is None:
            raise RuntimeError("信号模式保存失败。")
        return saved

    def delete_mode(self, mode_id: str) -> bool:
        self.ensure_table()
        if not self.get_mode(mode_id):
            return False
        self.db.execute(
            """
            UPDATE signal_modes
            SET deleted_at = ?, updated_at = ?
            WHERE id = ?
            """,
            [datetime.utcnow(), datetime.utcnow(), mode_id],
            write=True,
        )
        return True

    def _next_sort_order(self) -> int:
        current = self.db.scalar("SELECT COALESCE(MAX(sort_order), -1) FROM signal_modes WHERE deleted_at IS NULL")
        return int(current or 0) + 1

    def _decode(self, row: Dict[str, Any]) -> Dict[str, Any]:
        try:
            payload = json.loads(row.get("mode_json") or "{}")
        except json.JSONDecodeError:
            payload = {}
        payload["id"] = row["id"]
        payload.setdefault("name", row.get("name") or "新信号模式")
        mode = normalize_signal_mode(payload)
        mode["sort_order"] = row.get("sort_order")
        mode["created_at"] = row.get("created_at")
        mode["updated_at"] = row.get("updated_at")
        return mode

    def _json_payload(self, mode: Dict[str, Any]) -> Dict[str, Any]:
        return {
            key: value
            for key, value in mode.items()
            if key not in {"sort_order", "created_at", "updated_at", "deleted_at"}
        }
