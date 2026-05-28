from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from backend.app.db import Database
from backend.app.services.market_utils import safe_float, to_sina_chart_symbol


REVIEW_STATUSES = {"观察中", "有效", "误报", "已验证", "已放弃", "已错过", "归档"}
BATCH_REVIEW_STATUSES = {"观察中", "有效", "一般", "误报", "已归档"}


class WatchlistService:
    def __init__(self, db: Database):
        self.db = db

    def add_items(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        items = [item for item in payload.get("items") or [] if item.get("code")]
        batch_date = _date_value(payload.get("batch_date")) or _china_today()
        source_type = str(payload.get("source_type") or "manual")
        source_label = str(payload.get("source_label") or "观察池")
        source_ref = str(payload.get("source_ref") or "")
        source_summary = str(payload.get("source_summary") or "")
        batch_id = _batch_id(batch_date, source_type, source_label, source_ref)
        existing_batch = self.db.query("SELECT * FROM watchlist_batches WHERE id = ?", [batch_id])
        existing_batch_row = existing_batch[0] if existing_batch else {}
        if not source_summary:
            source_summary = str(existing_batch_row.get("source_summary") or "")
        now = datetime.utcnow()

        self.db.upsert(
            "watchlist_batches",
            [
                {
                    "id": batch_id,
                    "batch_date": batch_date,
                    "source_type": source_type,
                    "source_label": source_label,
                    "source_ref": source_ref,
                    "source_summary": source_summary,
                    "note": existing_batch_row.get("note") or payload.get("note") or "",
                    "review_status": _batch_review_status(existing_batch_row.get("review_status") or payload.get("review_status")),
                    "name": payload.get("name") or f"{source_label} · {_format_date(batch_date)}",
                    "status": "active",
                    "created_at": existing_batch_row.get("created_at") or now,
                    "updated_at": now,
                }
            ],
            ["id"],
        )

        stock_names = self._stock_names([item["code"] for item in items])
        rows = []
        hypothesis_rows = []
        for item in items:
            code = str(item["code"])
            entry_price = _first_number(
                item,
                ["entry_price", "latest_price", "latestPrice", "price"],
            )
            rows.append(
                {
                    "batch_id": batch_id,
                    "code": code,
                    "name": item.get("name") or stock_names.get(code) or code,
                    "entry_date": _date_value(item.get("entry_date")) or batch_date,
                    "entry_price": entry_price,
                    "source_type": source_type,
                    "source_label": source_label,
                    "source_ref": source_ref,
                    "signal_score": _first_number(item, ["signal_score", "radar_score", "score"]),
                    "signal_type": item.get("signal_type") or item.get("status") or source_label,
                    "chart_url": item.get("chart_url")
                    or f"https://finance.sina.com.cn/realstock/company/{to_sina_chart_symbol(code)}/nc.shtml",
                    "note": item.get("note") or "",
                    "review_status": _review_status(item.get("review_status")),
                    "reasons_json": json.dumps(item.get("reasons") or [], ensure_ascii=False),
                    "metrics_json": json.dumps(item.get("metrics") or {}, ensure_ascii=False),
                    "created_at": now,
                    "updated_at": now,
                }
            )
            if any(item.get(key) for key in ["hypothesis", "invalidation_rule", "trigger_rules", "tags"]):
                hypothesis_rows.append(
                    {
                        "id": f"{batch_id}:{code}",
                        "batch_id": batch_id,
                        "code": code,
                        "source_type": source_type,
                        "source_id": source_ref,
                        "hypothesis": item.get("hypothesis") or "",
                        "invalidation_rule": item.get("invalidation_rule") or "",
                        "entry_date": _date_value(item.get("entry_date")) or batch_date,
                        "entry_price": entry_price,
                        "review_status": _review_status(item.get("review_status")),
                        "trigger_rules_json": json.dumps(item.get("trigger_rules") or [], ensure_ascii=False),
                        "tags_json": json.dumps(item.get("tags") or [], ensure_ascii=False),
                        "created_at": now,
                        "updated_at": now,
                    }
                )
        added = self.db.upsert("watchlist_items", rows, ["batch_id", "code"])
        self.db.upsert("watchlist_hypotheses", hypothesis_rows, ["id"])
        return {"batch_id": batch_id, "added": added}

    def result(self, limit_batches: int = 20) -> Dict[str, Any]:
        batches = self.db.query(
            """
            SELECT *
            FROM watchlist_batches
            WHERE status != 'deleted'
            ORDER BY batch_date DESC, created_at DESC
            LIMIT ?
            """,
            [max(1, min(limit_batches, 100))],
        )
        batch_ids = [row["id"] for row in batches]
        if not batch_ids:
            return {"batches": [], "summary": self._summary([])}

        placeholders = ", ".join(["?"] * len(batch_ids))
        items = self.db.query(
            f"""
            SELECT i.*,
                   h.hypothesis,
                   h.invalidation_rule,
                   h.trigger_rules_json,
                   h.tags_json
            FROM watchlist_items i
            LEFT JOIN watchlist_hypotheses h
              ON h.batch_id = i.batch_id
             AND h.code = i.code
            WHERE i.batch_id IN ({placeholders})
            ORDER BY i.created_at, i.code
            """,
            batch_ids,
        )
        items_by_batch: Dict[str, List[Dict[str, Any]]] = {}
        for row in items:
            decoded = self._decode_item(row)
            items_by_batch.setdefault(decoded["batch_id"], []).append(decoded)

        enriched_batches = []
        for batch in batches:
            batch_items = [
                self._with_performance(item)
                for item in items_by_batch.get(batch["id"], [])
            ]
            enriched = dict(batch)
            enriched["note"] = enriched.get("note") or ""
            enriched["review_status"] = _batch_review_status(enriched.get("review_status"))
            enriched["items"] = batch_items
            enriched["item_count"] = len(batch_items)
            enriched.update(_batch_metrics(batch_items))
            enriched_batches.append(enriched)
        return {"batches": enriched_batches, "summary": self._summary(enriched_batches)}

    def delete_batch(self, batch_id: str) -> None:
        self.db.execute("DELETE FROM watchlist_hypotheses WHERE batch_id = ?", [batch_id], write=True)
        self.db.execute("DELETE FROM watchlist_items WHERE batch_id = ?", [batch_id], write=True)
        self.db.execute("DELETE FROM watchlist_batches WHERE id = ?", [batch_id], write=True)

    def delete_item(self, batch_id: str, code: str) -> None:
        self.db.execute(
            "DELETE FROM watchlist_hypotheses WHERE batch_id = ? AND code = ?",
            [batch_id, code],
            write=True,
        )
        self.db.execute(
            "DELETE FROM watchlist_items WHERE batch_id = ? AND code = ?",
            [batch_id, code],
            write=True,
        )

    def update_batch(self, batch_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        existing = self.db.query(
            "SELECT * FROM watchlist_batches WHERE id = ? LIMIT 1",
            [batch_id],
        )
        if not existing:
            return {"ok": False, "batch": None}
        note = str(payload.get("note") if payload.get("note") is not None else existing[0].get("note") or "")
        review_status = _batch_review_status(payload.get("review_status") or existing[0].get("review_status"))
        now = datetime.utcnow()
        self.db.execute(
            """
            UPDATE watchlist_batches
            SET note = ?, review_status = ?, updated_at = ?
            WHERE id = ?
            """,
            [note, review_status, now, batch_id],
            write=True,
        )
        batch = self.db.query("SELECT * FROM watchlist_batches WHERE id = ? LIMIT 1", [batch_id])
        return {"ok": bool(batch), "batch": batch[0] if batch else None}

    def update_item(self, batch_id: str, code: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        existing = self.db.query(
            """
            SELECT *
            FROM watchlist_items
            WHERE batch_id = ? AND code = ?
            LIMIT 1
            """,
            [batch_id, code],
        )
        if not existing:
            return {"ok": False, "item": None}
        note = str(payload.get("note") if payload.get("note") is not None else existing[0].get("note") or "")
        review_status = _review_status(payload.get("review_status") or existing[0].get("review_status"))
        now = datetime.utcnow()
        self.db.execute(
            """
            UPDATE watchlist_items
            SET note = ?, review_status = ?, updated_at = ?
            WHERE batch_id = ? AND code = ?
            """,
            [note, review_status, now, batch_id, code],
            write=True,
        )
        if any(key in payload for key in ["hypothesis", "invalidation_rule", "trigger_rules", "tags"]):
            current_h = self.db.query(
                "SELECT * FROM watchlist_hypotheses WHERE batch_id = ? AND code = ? LIMIT 1",
                [batch_id, code],
            )
            old = current_h[0] if current_h else {}
            self.db.upsert(
                "watchlist_hypotheses",
                [
                    {
                        "id": f"{batch_id}:{code}",
                        "batch_id": batch_id,
                        "code": code,
                        "source_type": existing[0].get("source_type"),
                        "source_id": existing[0].get("source_ref"),
                        "hypothesis": payload.get("hypothesis", old.get("hypothesis") or ""),
                        "invalidation_rule": payload.get("invalidation_rule", old.get("invalidation_rule") or ""),
                        "entry_date": existing[0].get("entry_date"),
                        "entry_price": existing[0].get("entry_price"),
                        "review_status": review_status,
                        "trigger_rules_json": json.dumps(payload.get("trigger_rules", json.loads(old.get("trigger_rules_json") or "[]")), ensure_ascii=False),
                        "tags_json": json.dumps(payload.get("tags", json.loads(old.get("tags_json") or "[]")), ensure_ascii=False),
                        "created_at": old.get("created_at") or now,
                        "updated_at": now,
                    }
                ],
                ["id"],
            )
        updated = self.db.query(
            """
            SELECT i.*,
                   h.hypothesis,
                   h.invalidation_rule,
                   h.trigger_rules_json,
                   h.tags_json
            FROM watchlist_items i
            LEFT JOIN watchlist_hypotheses h
              ON h.batch_id = i.batch_id
             AND h.code = i.code
            WHERE i.batch_id = ? AND i.code = ?
            LIMIT 1
            """,
            [batch_id, code],
        )
        item = self._with_performance(self._decode_item(updated[0])) if updated else None
        return {"ok": item is not None, "item": item}

    def _stock_names(self, codes: List[str]) -> Dict[str, str]:
        if not codes:
            return {}
        placeholders = ", ".join(["?"] * len(codes))
        rows = self.db.query(
            f"SELECT code, name FROM stock_basic WHERE code IN ({placeholders})",
            codes,
        )
        return {row["code"]: row["name"] for row in rows if row.get("name")}

    def _decode_item(self, row: Dict[str, Any]) -> Dict[str, Any]:
        decoded = dict(row)
        decoded["note"] = decoded.get("note") or ""
        decoded["review_status"] = _review_status(decoded.get("review_status"))
        decoded["reasons"] = json.loads(decoded.pop("reasons_json") or "[]")
        decoded["metrics"] = json.loads(decoded.pop("metrics_json") or "{}")
        decoded["hypothesis"] = decoded.get("hypothesis") or ""
        decoded["invalidation_rule"] = decoded.get("invalidation_rule") or ""
        decoded["trigger_rules"] = json.loads(decoded.pop("trigger_rules_json", None) or "[]")
        decoded["tags"] = json.loads(decoded.pop("tags_json", None) or "[]")
        return decoded

    def _with_performance(self, item: Dict[str, Any]) -> Dict[str, Any]:
        entry_date = _date_value(item.get("entry_date"))
        entry_price = safe_float(item.get("entry_price"))
        if entry_date is None:
            return _empty_performance(item)
        if entry_price is None or entry_price <= 0:
            entry_price = safe_float(
                self.db.scalar(
                    """
                    SELECT close
                    FROM historical_bars
                    WHERE code = ? AND date <= ?
                    ORDER BY date DESC
                    LIMIT 1
                    """,
                    [item["code"], entry_date],
                )
            )
        if entry_price is None or entry_price <= 0:
            return _empty_performance(item)
        future = self.db.query(
            """
            SELECT date, close, high, low
            FROM historical_bars
            WHERE code = ?
              AND date > ?
            ORDER BY date
            """,
            [item["code"], entry_date],
        )
        if not future:
            return {
                **item,
                "entry_price": entry_price,
                "days": 0,
                "latest_date": None,
                "latest_close": None,
                "return_latest": None,
                "return_1d": None,
                "return_3d": None,
                "return_5d": None,
                "return_10d": None,
                "max_return": None,
                "max_drawdown": None,
            }
        latest = future[-1]
        highs = [safe_float(row.get("high")) for row in future]
        lows = [safe_float(row.get("low")) for row in future]
        return {
            **item,
            "entry_price": entry_price,
            "days": len(future),
            "latest_date": latest.get("date"),
            "latest_close": safe_float(latest.get("close")),
            "return_latest": _return_from(entry_price, latest.get("close")),
            "return_1d": _return_at(future, entry_price, 1),
            "return_3d": _return_at(future, entry_price, 3),
            "return_5d": _return_at(future, entry_price, 5),
            "return_10d": _return_at(future, entry_price, 10),
            "max_return": (max(value for value in highs if value is not None) / entry_price - 1)
            if any(value is not None for value in highs)
            else None,
            "max_drawdown": (min(value for value in lows if value is not None) / entry_price - 1)
            if any(value is not None for value in lows)
            else None,
        }

    @staticmethod
    def _summary(batches: List[Dict[str, Any]]) -> Dict[str, Any]:
        items = [item for batch in batches for item in batch.get("items", [])]
        metrics = _batch_metrics(items)
        return {
            "batch_count": len(batches),
            "item_count": len(items),
            **metrics,
        }


def _empty_performance(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **item,
        "days": 0,
        "latest_date": None,
        "latest_close": None,
        "return_latest": None,
        "return_1d": None,
        "return_3d": None,
        "return_5d": None,
        "return_10d": None,
        "max_return": None,
        "max_drawdown": None,
    }


def _batch_metrics(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    values = _numeric_values(items, "return_latest")
    best_item = _extreme_item(items, reverse=True)
    worst_item = _extreme_item(items, reverse=False)
    return {
        "avg_return_latest": sum(values) / len(values) if values else None,
        "avg_return_1d": _avg(items, "return_1d"),
        "avg_return_3d": _avg(items, "return_3d"),
        "avg_return_5d": _avg(items, "return_5d"),
        "avg_return_10d": _avg(items, "return_10d"),
        "positive_count": sum(1 for value in values if value > 0),
        "positive_rate": sum(1 for value in values if value > 0) / len(values) if values else None,
        "hit_5pct_count": sum(
            1 for item in items if safe_float(item.get("max_return")) is not None and safe_float(item.get("max_return")) >= 0.05
        ),
        "hit_8pct_count": sum(
            1 for item in items if safe_float(item.get("max_return")) is not None and safe_float(item.get("max_return")) >= 0.08
        ),
        "hit_5pct_rate": _rate(items, "max_return", 0.05),
        "hit_8pct_rate": _rate(items, "max_return", 0.08),
        "worst_drawdown": min(_numeric_values(items, "max_drawdown")) if _numeric_values(items, "max_drawdown") else None,
        "best_item": best_item,
        "worst_item": worst_item,
    }


def _numeric_values(items: List[Dict[str, Any]], key: str) -> List[float]:
    values: List[float] = []
    for item in items:
        value = safe_float(item.get(key))
        if value is not None:
            values.append(value)
    return values


def _avg(items: List[Dict[str, Any]], key: str) -> Optional[float]:
    values = _numeric_values(items, key)
    return sum(values) / len(values) if values else None


def _rate(items: List[Dict[str, Any]], key: str, threshold: float) -> Optional[float]:
    values = _numeric_values(items, key)
    return sum(1 for value in values if value >= threshold) / len(values) if values else None


def _extreme_item(items: List[Dict[str, Any]], reverse: bool) -> Optional[Dict[str, Any]]:
    ranked = [
        item for item in items
        if safe_float(item.get("return_latest")) is not None
    ]
    if not ranked:
        return None
    item = sorted(ranked, key=lambda row: safe_float(row.get("return_latest")) or 0, reverse=reverse)[0]
    return {
        "code": item.get("code"),
        "name": item.get("name"),
        "return_latest": item.get("return_latest"),
        "return_5d": item.get("return_5d"),
        "max_return": item.get("max_return"),
        "max_drawdown": item.get("max_drawdown"),
    }


def _batch_id(batch_date: date, source_type: str, source_label: str, source_ref: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", source_type.lower()).strip("-") or "watch"
    digest = hashlib.sha1(f"{source_type}|{source_label}|{source_ref}".encode("utf-8")).hexdigest()[:8]
    return f"watch-{batch_date.strftime('%Y%m%d')}-{slug}-{digest}"


def _china_today() -> date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def _date_value(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _first_number(row: Dict[str, Any], keys: List[str]) -> Optional[float]:
    for key in keys:
        value = safe_float(row.get(key))
        if value is not None:
            return value
    return None


def _review_status(value: Any) -> str:
    status = str(value or "观察中")
    return status if status in REVIEW_STATUSES else "观察中"


def _batch_review_status(value: Any) -> str:
    status = str(value or "观察中")
    return status if status in BATCH_REVIEW_STATUSES else "观察中"


def _return_at(rows: List[Dict[str, Any]], entry_price: float, day: int) -> Optional[float]:
    if len(rows) < day:
        return None
    return _return_from(entry_price, rows[day - 1].get("close"))


def _return_from(entry_price: float, value: Any) -> Optional[float]:
    number = safe_float(value)
    if number is None or entry_price <= 0:
        return None
    return number / entry_price - 1


def _format_date(value: date) -> str:
    return value.strftime("%m-%d")
