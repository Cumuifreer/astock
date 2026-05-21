import json
from datetime import datetime, timedelta

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.data_service import DataService
from backend.app.services.strategy_service import DEFAULT_STRATEGY_CONFIG


def _run(run_id: str, signal_mode: str, finished_at: datetime, status: str = "completed_full") -> dict:
    config = {**DEFAULT_STRATEGY_CONFIG, "signal_mode": signal_mode}
    summary = {"candidate_count": 1, "zero_reason": None}
    return {
        "id": run_id,
        "status": status,
        "started_at": finished_at - timedelta(minutes=2),
        "finished_at": finished_at,
        "config_json": json.dumps(config, ensure_ascii=False),
        "summary_json": json.dumps(summary, ensure_ascii=False),
        "error_message": None,
    }


def test_analysis_reports_keep_recent_three_per_signal_mode(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    base = datetime(2026, 5, 21, 10, 0)
    rows = [
        _run("breakout-1", "platform_breakout", base + timedelta(minutes=1)),
        _run("breakout-2", "platform_breakout", base + timedelta(minutes=2)),
        _run("breakout-3", "platform_breakout", base + timedelta(minutes=3)),
        _run("breakout-4", "platform_breakout", base + timedelta(minutes=4)),
        _run("setup-1", "platform_setup", base + timedelta(minutes=5)),
        _run("setup-2", "platform_setup", base + timedelta(minutes=6)),
        _run("failed-1", "platform_setup", base + timedelta(minutes=7), status="failed"),
    ]
    db.upsert("analysis_runs", rows, ["id"])

    result = DataService(db).analysis_reports(per_mode_limit=3)

    groups = {group["signal_mode"]: group["reports"] for group in result["groups"]}
    assert [report["id"] for report in groups["platform_breakout"]] == [
        "breakout-4",
        "breakout-3",
        "breakout-2",
    ]
    assert [report["id"] for report in groups["platform_setup"]] == ["setup-2", "setup-1"]
    assert "failed-1" not in [report["id"] for group in result["groups"] for report in group["reports"]]


def test_analysis_report_returns_selected_run_candidates_and_funnel(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    finished_at = datetime(2026, 5, 21, 10, 0)
    db.upsert("analysis_runs", [_run("run-1", "platform_setup", finished_at)], ["id"])
    db.upsert(
        "funnel_stats",
        [
            {
                "run_id": "run-1",
                "order_index": 0,
                "step_name": "平台压缩",
                "before_count": 10,
                "after_count": 3,
                "removed_count": 7,
                "note": "压缩区间",
            }
        ],
        ["run_id", "order_index"],
    )
    db.upsert(
        "candidate_results",
        [
            {
                "run_id": "run-1",
                "rank": 1,
                "code": "000001.SZ",
                "name": "平安银行",
                "latest_price": 10.0,
                "pct_chg": 1.2,
                "amount": 100_000_000,
                "volume": 1000,
                "turnover_rate": 2.0,
                "amplitude": 0.03,
                "rps20": 70.0,
                "rps60": None,
                "rps120": None,
                "ma_short": 10.0,
                "ma_long": 9.5,
                "float_market_value": 30_000_000_000,
                "signal_type": "平台临界",
                "signal_score": 88.0,
                "data_sources": "{}",
                "reasons_json": json.dumps(["距平台上沿 1.20%"], ensure_ascii=False),
                "chart_url": "https://finance.sina.com.cn",
                "metrics_json": "{}",
                "created_at": finished_at,
            }
        ],
        ["run_id", "code"],
    )

    report = DataService(db).analysis_report("run-1")

    assert report["analysis"]["id"] == "run-1"
    assert report["candidates"]["rows"][0]["code"] == "000001.SZ"
    assert report["candidates"]["funnel"][0]["step_name"] == "平台压缩"
