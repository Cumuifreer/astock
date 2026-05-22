from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from backend.app.db import Database
from backend.app.services.market_utils import safe_float, to_sina_chart_symbol


class WatchlistService:
    def __init__(self, db: Database):
        self.db = db

    def add_items(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        items = [item for item in payload.get("items") or [] if item.get("code")]
        batch_date = _date_value(payload.get("batch_date")) or _china_today()
        source_type = str(payload.get("source_type") or "manual")
        source_label = str(payload.get("source_label") or "观察池")
        source_ref = str(payload.get("source_ref") or "")
        batch_id = _batch_id(batch_date, source_type, source_label, source_ref)
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
                    "name": payload.get("name") or f"{source_label} · {_format_date(batch_date)}",
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                }
            ],
            ["id"],
        )

        stock_names = self._stock_names([item["code"] for item in items])
        rows = []
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
                    "reasons_json": json.dumps(item.get("reasons") or [], ensure_ascii=False),
                    "metrics_json": json.dumps(item.get("metrics") or {}, ensure_ascii=False),
                    "created_at": now,
                    "updated_at": now,
                }
            )
        added = self.db.upsert("watchlist_items", rows, ["batch_id", "code"])
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
            SELECT *
            FROM watchlist_items
            WHERE batch_id IN ({placeholders})
            ORDER BY created_at, code
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
            enriched["items"] = batch_items
            enriched["item_count"] = len(batch_items)
            enriched.update(_batch_metrics(batch_items))
            enriched_batches.append(enriched)
        return {"batches": enriched_batches, "summary": self._summary(enriched_batches)}

    def delete_batch(self, batch_id: str) -> None:
        self.db.execute("DELETE FROM watchlist_items WHERE batch_id = ?", [batch_id], write=True)
        self.db.execute("DELETE FROM watchlist_batches WHERE id = ?", [batch_id], write=True)

    def delete_item(self, batch_id: str, code: str) -> None:
        self.db.execute(
            "DELETE FROM watchlist_items WHERE batch_id = ? AND code = ?",
            [batch_id, code],
            write=True,
        )

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
        decoded["reasons"] = json.loads(decoded.pop("reasons_json") or "[]")
        decoded["metrics"] = json.loads(decoded.pop("metrics_json") or "{}")
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
        latest_returns = [
            safe_float(item.get("return_latest"))
            for item in items
            if safe_float(item.get("return_latest")) is not None
        ]
        return {
            "batch_count": len(batches),
            "item_count": len(items),
            "avg_return_latest": sum(latest_returns) / len(latest_returns) if latest_returns else None,
            "positive_count": sum(1 for value in latest_returns if value > 0),
            "hit_5pct_count": sum(
                1 for item in items if safe_float(item.get("max_return")) is not None and safe_float(item.get("max_return")) >= 0.05
            ),
            "hit_8pct_count": sum(
                1 for item in items if safe_float(item.get("max_return")) is not None and safe_float(item.get("max_return")) >= 0.08
            ),
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
    values = [
        safe_float(item.get("return_latest"))
        for item in items
        if safe_float(item.get("return_latest")) is not None
    ]
    return {
        "avg_return_latest": sum(values) / len(values) if values else None,
        "positive_count": sum(1 for value in values if value > 0),
        "hit_5pct_count": sum(
            1 for item in items if safe_float(item.get("max_return")) is not None and safe_float(item.get("max_return")) >= 0.05
        ),
        "hit_8pct_count": sum(
            1 for item in items if safe_float(item.get("max_return")) is not None and safe_float(item.get("max_return")) >= 0.08
        ),
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
