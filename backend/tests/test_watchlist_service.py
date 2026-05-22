from datetime import date, timedelta

import pytest

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.watchlist_service import WatchlistService


def _seed_stock_with_bars(db: Database, code: str = "000001.SZ", closes=None) -> None:
    db.upsert(
        "stock_basic",
        [
            {
                "code": code,
                "name": "平安银行",
                "exchange": "SZ",
                "list_date": "1991-04-03",
                "source": "test",
                "is_st": False,
                "suspended": False,
                "updated_at": "2026-01-01T00:00:00",
            }
        ],
        ["code"],
    )
    rows = []
    start = date(2026, 5, 20)
    closes = closes or [10.0, 10.5, 10.2, 11.0, 11.5, 10.8, 12.0, 12.5, 11.7, 13.0, 12.8]
    for offset, close in enumerate(closes):
        rows.append(
            {
                "code": code,
                "date": start + timedelta(days=offset),
                "open": close - 0.2,
                "high": close + 0.5,
                "low": close - 0.4,
                "close": close,
                "prev_close": closes[offset - 1] if offset else close,
                "volume": 1000 + offset,
                "amount": 10_000 + offset,
                "turn": 2.0,
                "pct_chg": 1.0,
                "tradestatus": "1",
                "is_st": False,
                "source": "Baostock",
                "updated_at": "2026-05-20T00:00:00",
            }
        )
    db.upsert("historical_bars", rows, ["code", "date"])


def test_watchlist_groups_items_and_computes_forward_returns(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    _seed_stock_with_bars(db)

    service = WatchlistService(db)
    created = service.add_items(
        {
            "source_type": "analysis",
            "source_label": "平台突破",
            "source_ref": "analysis-1",
            "batch_date": "2026-05-20",
            "items": [
                {
                    "code": "000001.SZ",
                    "name": "平安银行",
                    "entry_price": 10.0,
                    "signal_score": 88.0,
                    "signal_type": "平台突破",
                    "reasons": ["平台突破"],
                    "metrics": {"rps20": 80},
                }
            ],
        }
    )

    result = service.result()
    batch = result["batches"][0]
    item = batch["items"][0]

    assert created["added"] == 1
    assert batch["batch_date"] == date(2026, 5, 20)
    assert batch["source_label"] == "平台突破"
    assert batch["item_count"] == 1
    assert item["code"] == "000001.SZ"
    assert item["return_1d"] == pytest.approx(0.05)
    assert item["return_3d"] == pytest.approx(0.10)
    assert item["return_5d"] == pytest.approx(0.08)
    assert item["return_10d"] == pytest.approx(0.28)
    assert item["max_return"] == pytest.approx(0.35)
    assert item["max_drawdown"] == pytest.approx(-0.02)
    assert item["reasons"] == ["平台突破"]
    assert item["metrics"] == {"rps20": 80}
    assert batch["avg_return_1d"] == pytest.approx(0.05)
    assert batch["avg_return_3d"] == pytest.approx(0.10)
    assert batch["avg_return_5d"] == pytest.approx(0.08)
    assert batch["avg_return_10d"] == pytest.approx(0.28)
    assert batch["positive_rate"] == pytest.approx(1.0)
    assert batch["hit_5pct_rate"] == pytest.approx(1.0)
    assert batch["hit_8pct_rate"] == pytest.approx(1.0)
    assert batch["worst_drawdown"] == pytest.approx(-0.02)


def test_watchlist_reuses_batch_and_deletes_items(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    _seed_stock_with_bars(db, "000001.SZ")
    _seed_stock_with_bars(db, "000002.SZ")
    service = WatchlistService(db)

    first = service.add_items(
        {
            "source_type": "intraday",
            "source_label": "盘中雷达 · 严格筛选",
            "batch_date": "2026-05-20",
            "items": [{"code": "000001.SZ", "entry_price": 10.0}],
        }
    )
    second = service.add_items(
        {
            "source_type": "intraday",
            "source_label": "盘中雷达 · 严格筛选",
            "batch_date": "2026-05-20",
            "items": [{"code": "000002.SZ", "entry_price": 10.0}],
        }
    )

    assert first["batch_id"] == second["batch_id"]
    assert service.result()["batches"][0]["item_count"] == 2

    service.delete_item(first["batch_id"], "000001.SZ")
    result = service.result()

    assert result["batches"][0]["item_count"] == 1
    assert result["batches"][0]["items"][0]["code"] == "000002.SZ"


def test_watchlist_updates_item_note_and_status(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    _seed_stock_with_bars(db)
    service = WatchlistService(db)

    created = service.add_items(
        {
            "source_type": "analysis",
            "source_label": "平台临界",
            "source_summary": "平台临界 · 20日 · 距上沿≤3.50%",
            "batch_date": "2026-05-20",
            "items": [{"code": "000001.SZ", "entry_price": 10.0}],
        }
    )
    service.update_item(
        created["batch_id"],
        "000001.SZ",
        {"note": "次日缩量，继续看 10 日线。", "review_status": "观察中"},
    )

    batch = service.result()["batches"][0]
    item = batch["items"][0]

    assert batch["source_summary"] == "平台临界 · 20日 · 距上沿≤3.50%"
    assert item["note"] == "次日缩量，继续看 10 日线。"
    assert item["review_status"] == "观察中"


def test_watchlist_updates_batch_review_and_highlights_best_worst(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    _seed_stock_with_bars(db, "000001.SZ")
    _seed_stock_with_bars(
        db,
        "000002.SZ",
        closes=[10.0, 9.8, 9.6, 9.4, 9.2, 9.0, 8.8, 8.7, 8.6, 8.5, 8.4],
    )
    service = WatchlistService(db)
    created = service.add_items(
        {
            "source_type": "analysis",
            "source_label": "平台临界",
            "batch_date": "2026-05-20",
            "items": [
                {"code": "000001.SZ", "entry_price": 10.0},
                {"code": "000002.SZ", "entry_price": 10.0},
            ],
        }
    )

    updated = service.update_batch(
        created["batch_id"],
        {"note": "弱市样本，继续观察 T+5。", "review_status": "有效"},
    )
    batch = service.result()["batches"][0]

    assert updated["ok"] is True
    assert batch["note"] == "弱市样本，继续观察 T+5。"
    assert batch["review_status"] == "有效"
    assert batch["best_item"]["code"] == "000001.SZ"
    assert batch["worst_item"]["code"] == "000002.SZ"
    assert batch["avg_return_5d"] == pytest.approx(-0.01)
