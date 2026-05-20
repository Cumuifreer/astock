import pandas as pd

from backend.app.services.analysis_service import (
    apply_strategy_filters,
    compute_amplitude,
    compute_rps_scores,
)
from backend.app.services.strategy_service import DEFAULT_STRATEGY_CONFIG


def test_compute_amplitude_uses_previous_close():
    assert compute_amplitude(high=12.0, low=10.0, prev_close=10.0) == 0.2
    assert compute_amplitude(high=12.0, low=10.0, prev_close=0.0) is None
    assert compute_amplitude(high=None, low=10.0, prev_close=10.0) is None


def test_rps_scores_rank_recent_returns_by_percentile():
    closes = pd.DataFrame(
        [
            {"code": "000001.SZ", "date": "2026-01-01", "close": 10.0},
            {"code": "000001.SZ", "date": "2026-01-21", "close": 11.0},
            {"code": "600000.SH", "date": "2026-01-01", "close": 10.0},
            {"code": "600000.SH", "date": "2026-01-21", "close": 12.0},
            {"code": "300750.SZ", "date": "2026-01-01", "close": 10.0},
            {"code": "300750.SZ", "date": "2026-01-21", "close": 9.0},
        ]
    )

    scores = compute_rps_scores(closes, windows=(20,))

    assert scores["600000.SH"]["rps20"] == 100.0
    assert scores["000001.SZ"]["rps20"] == 66.67
    assert scores["300750.SZ"]["rps20"] == 33.33


def test_strategy_filters_keep_explainable_candidates():
    rows = pd.DataFrame(
        [
            {
                "code": "000001.SZ",
                "name": "平安银行",
                "latest_price": 12.5,
                "amount": 900_000_000,
                "float_market_value": 80_000_000_000,
                "ma_short": 12.0,
                "ma_long": 10.0,
                "rps20": 88.0,
                "turnover_rate": 4.2,
                "pct_chg": 3.0,
                "amplitude": 0.05,
                "volume_ratio": 1.7,
                "ma_distance": 0.04,
                "is_st": False,
                "suspended": False,
            },
            {
                "code": "600000.SH",
                "name": "浦发银行",
                "latest_price": 8.0,
                "amount": 30_000_000,
                "float_market_value": None,
                "ma_short": 7.5,
                "ma_long": 8.0,
                "rps20": 42.0,
                "turnover_rate": None,
                "pct_chg": -1.0,
                "amplitude": 0.02,
                "volume_ratio": 0.7,
                "ma_distance": 0.03,
                "is_st": False,
                "suspended": False,
            },
        ]
    )
    config = {
        **DEFAULT_STRATEGY_CONFIG,
        "min_price": 5,
        "min_amount": 100_000_000,
        "min_rps20": 70,
        "candidate_limit": 10,
    }

    candidates, funnel, zero_reason = apply_strategy_filters(rows, config)

    assert [row["code"] for row in candidates] == ["000001.SZ"]
    assert zero_reason is None
    assert funnel[-1]["after_count"] == 1
    assert any("成交额" in reason for reason in candidates[0]["reasons"])
