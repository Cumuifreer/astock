from datetime import date, timedelta

import pandas as pd

from backend.app.services.analysis_service import (
    apply_strategy_filters,
    compute_amplitude,
    compute_platform_breakout_metrics,
    compute_platform_setup_metrics,
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


def test_platform_breakout_metrics_detect_compression_and_volume_breakout():
    bars = []
    start = date(2026, 4, 1)
    for index in range(35):
        close = 10.0 + index * 0.02
        bullish = index % 3 != 0
        bars.append(
            {
                "code": "000001.SZ",
                "date": (start + timedelta(days=index)).isoformat(),
                "open": close - 0.03 if bullish else close + 0.03,
                "high": close + 0.06,
                "low": close - 0.06,
                "close": close,
                "prev_close": close - 0.02,
                "volume": 1300 if bullish else 900,
                "pct_chg": 0.2,
            }
        )
    bars.append(
        {
            "code": "000001.SZ",
            "date": "2026-05-20",
            "open": 10.72,
            "high": 11.72,
            "low": 10.62,
            "close": 11.55,
            "prev_close": 10.68,
            "volume": 3600,
            "pct_chg": 8.15,
        }
    )

    metrics = compute_platform_breakout_metrics(pd.DataFrame(bars), DEFAULT_STRATEGY_CONFIG)

    assert metrics["platform_ready"] is True
    assert metrics["platform_range"] <= 0.08
    assert metrics["platform_bullish_ratio"] >= 0.5
    assert metrics["platform_bull_volume_ratio"] > 1.1
    assert metrics["platform_breakout_volume_ratio"] > 2.5
    assert metrics["platform_breakout_bullish"] is True
    assert metrics["platform_upper"] < metrics["platform_breakout_close"]
    assert metrics["platform_breakout_clearance"] > 0
    assert metrics["platform_breakout_above_upper"] is True
    assert metrics["platform_first_breakout"] is True
    assert metrics["platform_body_strength"] > 1
    assert metrics["platform_ma_bullish"] is True
    assert metrics["platform_ma_rising"] is True
    assert metrics["macd_dif"] > 0
    assert metrics["macd_dea"] > 0


def test_platform_breakout_metrics_can_use_close_range_to_ignore_wicks():
    bars = []
    start = date(2026, 4, 1)
    for index in range(20):
        close = 10.0 + (index % 4) * 0.03
        bars.append(
            {
                "code": "000001.SZ",
                "date": (start + timedelta(days=index)).isoformat(),
                "open": close - 0.02,
                "high": 10.9 if index == 4 else close + 0.08,
                "low": 9.7 if index == 9 else close - 0.08,
                "close": close,
                "prev_close": close - 0.02,
                "volume": 1000,
                "pct_chg": 0.2,
            }
        )
    bars.append(
        {
            "code": "000001.SZ",
            "date": "2026-05-20",
            "open": 10.05,
            "high": 10.86,
            "low": 10.0,
            "close": 10.76,
            "prev_close": 10.05,
            "volume": 3100,
            "pct_chg": 7.06,
        }
    )

    high_low = compute_platform_breakout_metrics(
        pd.DataFrame(bars),
        {**DEFAULT_STRATEGY_CONFIG, "platform_range_basis": "high_low"},
    )
    close_range = compute_platform_breakout_metrics(
        pd.DataFrame(bars),
        {**DEFAULT_STRATEGY_CONFIG, "platform_range_basis": "close"},
    )

    assert high_low["platform_range"] > 0.1
    assert close_range["platform_range"] < 0.02
    assert close_range["platform_breakout_above_upper"] is True


def test_platform_breakout_metrics_marks_non_first_breakout_after_prior_cross():
    bars = []
    start = date(2026, 4, 1)
    for index in range(22):
        close = 10.0 + (index % 3) * 0.02
        if index == 20:
            close = 10.8
        if index == 21:
            close = 11.0
        bars.append(
            {
                "code": "000001.SZ",
                "date": (start + timedelta(days=index)).isoformat(),
                "open": close - 0.04,
                "high": close + 0.06,
                "low": close - 0.06,
                "close": close,
                "prev_close": close - 0.02,
                "volume": 1000,
                "pct_chg": 2.0,
            }
        )

    metrics = compute_platform_breakout_metrics(pd.DataFrame(bars), DEFAULT_STRATEGY_CONFIG)

    assert metrics["platform_breakout_above_upper"] is True
    assert metrics["platform_first_breakout"] is False


def test_platform_setup_metrics_detect_near_upper_compression_before_breakout():
    bars = []
    start = date(2026, 4, 1)
    for index in range(30):
        close = 10.0 + min(index, 20) * 0.025
        bullish = index % 3 != 0
        bars.append(
            {
                "code": "000001.SZ",
                "date": (start + timedelta(days=index)).isoformat(),
                "open": close - 0.025 if bullish else close + 0.025,
                "high": close + 0.07,
                "low": close - 0.07,
                "close": close,
                "prev_close": close - 0.02,
                "volume": 900 if index >= 25 else 1300 if bullish else 950,
                "pct_chg": 0.2,
            }
        )
    bars[-1]["close"] = 10.54
    bars[-1]["high"] = 10.62
    bars[-1]["low"] = 10.43
    bars[-1]["volume"] = 920

    metrics = compute_platform_setup_metrics(pd.DataFrame(bars), DEFAULT_STRATEGY_CONFIG)

    assert metrics["platform_setup_ready"] is True
    assert metrics["platform_setup_range"] <= 0.12
    assert metrics["platform_setup_distance_to_high"] <= 0.035
    assert metrics["platform_setup_recent_gain_5d"] <= 0.1
    assert metrics["platform_setup_volume_contraction"] <= 1.0
    assert metrics["platform_setup_ma_turning_up"] is True


def test_platform_breakout_filters_keep_matching_shape():
    rows = pd.DataFrame(
        [
            {
                "code": "000001.SZ",
                "name": "平安银行",
                "latest_price": 11.55,
                "amount": 900_000_000,
                "float_market_value": 80_000_000_000,
                "ma_short": 11.1,
                "ma_long": 10.6,
                "rps20": 88.0,
                "turnover_rate": 4.2,
                "pct_chg": 8.15,
                "amplitude": 0.1,
                "volume_ratio": 2.7,
                "ma_distance": 0.04,
                "platform_ready": True,
                "platform_range": 0.07,
                "platform_bullish_ratio": 0.6,
                "platform_bull_volume_ratio": 1.2,
                "platform_breakout_volume_ratio": 2.8,
                "platform_breakout_bullish": True,
                "platform_breakout_pct_chg": 8.15,
                "platform_breakout_clearance": 0.03,
                "platform_breakout_above_upper": True,
                "platform_first_breakout": True,
                "platform_body_strength": 1.3,
                "platform_ma_bullish": True,
                "platform_ma_rising": True,
                "macd_dif": 0.12,
                "macd_dea": 0.08,
                "is_st": False,
                "suspended": False,
            },
            {
                "code": "600000.SH",
                "name": "浦发银行",
                "latest_price": 8.0,
                "amount": 900_000_000,
                "float_market_value": 80_000_000_000,
                "ma_short": 8.2,
                "ma_long": 8.1,
                "rps20": 90.0,
                "turnover_rate": 3.0,
                "pct_chg": 6.0,
                "amplitude": 0.09,
                "volume_ratio": 2.6,
                "ma_distance": 0.02,
                "platform_ready": True,
                "platform_range": 0.13,
                "platform_bullish_ratio": 0.65,
                "platform_bull_volume_ratio": 1.3,
                "platform_breakout_volume_ratio": 3.0,
                "platform_breakout_bullish": True,
                "platform_breakout_pct_chg": 6.0,
                "platform_breakout_clearance": -0.01,
                "platform_breakout_above_upper": False,
                "platform_first_breakout": False,
                "platform_body_strength": 1.4,
                "platform_ma_bullish": True,
                "platform_ma_rising": True,
                "macd_dif": 0.2,
                "macd_dea": 0.1,
                "is_st": False,
                "suspended": False,
            },
        ]
    )
    config = {
        **DEFAULT_STRATEGY_CONFIG,
        "signal_mode": "platform_breakout",
        "min_price": 5,
        "min_amount": 100_000_000,
        "min_rps20": 70,
        "candidate_limit": 10,
    }

    candidates, funnel, zero_reason = apply_strategy_filters(rows, config)

    assert [row["code"] for row in candidates] == ["000001.SZ"]
    assert candidates[0]["signal_type"] == "平台突破"
    assert zero_reason is None
    assert any(step["step_name"] == "平台振幅" for step in funnel)
    assert any(step["step_name"] == "突破上沿" for step in funnel)
    assert any("平台振幅" in reason for reason in candidates[0]["reasons"])
    assert any("突破上沿" in reason for reason in candidates[0]["reasons"])


def test_platform_breakout_filters_remove_overheated_clearance_when_required():
    rows = pd.DataFrame(
        [
            {
                "code": "000001.SZ",
                "name": "平安银行",
                "latest_price": 11.0,
                "amount": 900_000_000,
                "float_market_value": 80_000_000_000,
                "ma_short": 10.8,
                "ma_long": 10.2,
                "rps20": 88.0,
                "turnover_rate": 4.2,
                "pct_chg": 6.0,
                "amplitude": 0.1,
                "volume_ratio": 2.7,
                "ma_distance": 0.04,
                "platform_ready": True,
                "platform_range": 0.07,
                "platform_bullish_ratio": 0.6,
                "platform_bull_volume_ratio": 1.2,
                "platform_breakout_volume_ratio": 2.8,
                "platform_breakout_bullish": True,
                "platform_breakout_pct_chg": 6.0,
                "platform_breakout_clearance": 0.08,
                "platform_breakout_above_upper": True,
                "platform_first_breakout": True,
                "platform_body_strength": 1.3,
                "platform_ma_bullish": True,
                "platform_ma_rising": True,
                "macd_dif": 0.12,
                "macd_dea": 0.08,
                "is_st": False,
                "suspended": False,
            },
            {
                "code": "600000.SH",
                "name": "浦发银行",
                "latest_price": 12.0,
                "amount": 900_000_000,
                "float_market_value": 80_000_000_000,
                "ma_short": 11.5,
                "ma_long": 10.5,
                "rps20": 90.0,
                "turnover_rate": 3.0,
                "pct_chg": 8.0,
                "amplitude": 0.09,
                "volume_ratio": 2.6,
                "ma_distance": 0.02,
                "platform_ready": True,
                "platform_range": 0.07,
                "platform_bullish_ratio": 0.65,
                "platform_bull_volume_ratio": 1.3,
                "platform_breakout_volume_ratio": 3.0,
                "platform_breakout_bullish": True,
                "platform_breakout_pct_chg": 8.0,
                "platform_breakout_clearance": 0.22,
                "platform_breakout_above_upper": True,
                "platform_first_breakout": False,
                "platform_body_strength": 1.4,
                "platform_ma_bullish": True,
                "platform_ma_rising": True,
                "macd_dif": 0.2,
                "macd_dea": 0.1,
                "is_st": False,
                "suspended": False,
            },
        ]
    )
    config = {
        **DEFAULT_STRATEGY_CONFIG,
        "signal_mode": "platform_breakout",
        "min_price": 5,
        "min_amount": 100_000_000,
        "min_rps20": 70,
        "platform_breakout_max_clearance": 0.15,
        "platform_breakout_max_clearance_mode": "must",
        "platform_breakout_first_mode": "off",
        "candidate_limit": 10,
    }

    candidates, funnel, zero_reason = apply_strategy_filters(rows, config)

    assert [row["code"] for row in candidates] == ["000001.SZ"]
    assert zero_reason is None
    assert any(step["step_name"] == "突破距离" for step in funnel)


def test_platform_breakout_score_mode_keeps_but_penalizes_overextended_breakouts():
    rows = pd.DataFrame(
        [
            {
                "code": "000001.SZ",
                "name": "平安银行",
                "latest_price": 11.0,
                "amount": 900_000_000,
                "float_market_value": 80_000_000_000,
                "ma_short": 10.8,
                "ma_long": 10.2,
                "rps20": 88.0,
                "turnover_rate": 4.2,
                "pct_chg": 6.0,
                "amplitude": 0.1,
                "volume_ratio": 2.7,
                "ma_distance": 0.04,
                "platform_ready": True,
                "platform_range": 0.07,
                "platform_bullish_ratio": 0.6,
                "platform_bull_volume_ratio": 1.2,
                "platform_breakout_volume_ratio": 2.8,
                "platform_breakout_bullish": True,
                "platform_breakout_pct_chg": 6.0,
                "platform_breakout_clearance": 0.08,
                "platform_breakout_above_upper": True,
                "platform_first_breakout": True,
                "platform_body_strength": 1.3,
                "platform_ma_bullish": True,
                "platform_ma_rising": True,
                "macd_dif": 0.12,
                "macd_dea": 0.08,
                "is_st": False,
                "suspended": False,
            },
            {
                "code": "600000.SH",
                "name": "浦发银行",
                "latest_price": 12.0,
                "amount": 900_000_000,
                "float_market_value": 80_000_000_000,
                "ma_short": 11.5,
                "ma_long": 10.5,
                "rps20": 90.0,
                "turnover_rate": 3.0,
                "pct_chg": 8.0,
                "amplitude": 0.09,
                "volume_ratio": 2.6,
                "ma_distance": 0.02,
                "platform_ready": True,
                "platform_range": 0.07,
                "platform_bullish_ratio": 0.65,
                "platform_bull_volume_ratio": 1.3,
                "platform_breakout_volume_ratio": 3.0,
                "platform_breakout_bullish": True,
                "platform_breakout_pct_chg": 8.0,
                "platform_breakout_clearance": 0.22,
                "platform_breakout_above_upper": True,
                "platform_first_breakout": False,
                "platform_body_strength": 1.4,
                "platform_ma_bullish": True,
                "platform_ma_rising": True,
                "macd_dif": 0.2,
                "macd_dea": 0.1,
                "is_st": False,
                "suspended": False,
            },
        ]
    )
    config = {
        **DEFAULT_STRATEGY_CONFIG,
        "signal_mode": "platform_breakout",
        "min_price": 5,
        "min_amount": 100_000_000,
        "min_rps20": 70,
        "platform_breakout_max_clearance": 0.15,
        "platform_breakout_max_clearance_mode": "score",
        "platform_breakout_first_mode": "score",
        "candidate_limit": 10,
    }

    candidates, _, zero_reason = apply_strategy_filters(rows, config)

    assert {row["code"] for row in candidates} == {"000001.SZ", "600000.SH"}
    scores = {row["code"]: row["signal_score"] for row in candidates}
    assert scores["000001.SZ"] > scores["600000.SH"]
    assert zero_reason is None


def test_platform_setup_filters_keep_near_upper_not_overheated_candidates():
    rows = pd.DataFrame(
        [
            {
                "code": "000001.SZ",
                "name": "平安银行",
                "latest_price": 10.6,
                "amount": 180_000_000,
                "float_market_value": 40_000_000_000,
                "ma_short": 10.45,
                "ma_long": 10.1,
                "rps20": 72.0,
                "turnover_rate": 3.2,
                "pct_chg": 1.5,
                "amplitude": 0.04,
                "volume_ratio": 0.75,
                "ma_distance": 0.02,
                "platform_setup_ready": True,
                "platform_setup_range": 0.08,
                "platform_setup_distance_to_high": 0.018,
                "platform_setup_recent_gain_5d": 0.035,
                "platform_setup_volume_contraction": 0.78,
                "platform_setup_bull_volume_ratio": 1.15,
                "platform_setup_ma_convergence": 0.028,
                "platform_setup_ma_turning_up": True,
                "macd_dif": 0.02,
                "macd_dea": 0.01,
                "is_st": False,
                "suspended": False,
            },
            {
                "code": "600000.SH",
                "name": "浦发银行",
                "latest_price": 8.0,
                "amount": 200_000_000,
                "float_market_value": 50_000_000_000,
                "ma_short": 8.2,
                "ma_long": 8.0,
                "rps20": 80.0,
                "turnover_rate": 2.5,
                "pct_chg": 0.8,
                "amplitude": 0.03,
                "volume_ratio": 0.7,
                "ma_distance": 0.03,
                "platform_setup_ready": True,
                "platform_setup_range": 0.07,
                "platform_setup_distance_to_high": 0.08,
                "platform_setup_recent_gain_5d": 0.02,
                "platform_setup_volume_contraction": 0.8,
                "platform_setup_bull_volume_ratio": 1.3,
                "platform_setup_ma_convergence": 0.02,
                "platform_setup_ma_turning_up": True,
                "macd_dif": 0.03,
                "macd_dea": 0.01,
                "is_st": False,
                "suspended": False,
            },
            {
                "code": "300750.SZ",
                "name": "宁德时代",
                "latest_price": 210.0,
                "amount": 600_000_000,
                "float_market_value": 200_000_000_000,
                "ma_short": 205.0,
                "ma_long": 190.0,
                "rps20": 92.0,
                "turnover_rate": 4.0,
                "pct_chg": 5.0,
                "amplitude": 0.07,
                "volume_ratio": 2.0,
                "ma_distance": 0.06,
                "platform_setup_ready": True,
                "platform_setup_range": 0.09,
                "platform_setup_distance_to_high": 0.01,
                "platform_setup_recent_gain_5d": 0.16,
                "platform_setup_volume_contraction": 1.5,
                "platform_setup_bull_volume_ratio": 1.4,
                "platform_setup_ma_convergence": 0.06,
                "platform_setup_ma_turning_up": True,
                "macd_dif": 0.5,
                "macd_dea": 0.4,
                "is_st": False,
                "suspended": False,
            },
        ]
    )
    config = {
        **DEFAULT_STRATEGY_CONFIG,
        "signal_mode": "platform_setup",
        "min_price": 5,
        "min_amount": 100_000_000,
        "min_rps20": 60,
        "platform_setup_max_range": 0.1,
        "platform_setup_max_distance_to_high": 0.035,
        "platform_setup_max_recent_gain_5d": 0.1,
        "platform_setup_volume_contraction_max": 1.05,
        "platform_setup_bull_volume_advantage": 1.05,
        "platform_setup_ma_convergence_max": 0.05,
        "volume_ratio_min": 1.1,
        "candidate_limit": 10,
    }

    candidates, funnel, zero_reason = apply_strategy_filters(rows, config)

    assert [row["code"] for row in candidates] == ["000001.SZ"]
    assert candidates[0]["signal_type"] == "平台临界"
    assert zero_reason is None
    assert "成交量放大" not in [step["step_name"] for step in funnel]
    assert any(step["step_name"] == "接近平台上沿" for step in funnel)
    assert any("距平台上沿" in reason for reason in candidates[0]["reasons"])


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


def test_score_analysis_mode_ranks_near_matches_without_signal_hard_filters():
    rows = pd.DataFrame(
        [
            {
                "code": "000001.SZ",
                "name": "平安银行",
                "latest_price": 12.5,
                "amount": 180_000_000,
                "float_market_value": 80_000_000_000,
                "ma_short": 12.0,
                "ma_long": 10.0,
                "rps20": 62.0,
                "turnover_rate": 4.2,
                "pct_chg": 4.2,
                "amplitude": 0.11,
                "volume_ratio": 1.5,
                "ma_distance": 0.04,
                "platform_ready": True,
                "platform_range": 0.16,
                "platform_bullish_ratio": 0.45,
                "platform_bull_volume_ratio": 1.05,
                "platform_breakout_volume_ratio": 1.8,
                "platform_breakout_bullish": True,
                "platform_breakout_pct_chg": 4.2,
                "platform_body_strength": 0.9,
                "platform_ma_bullish": True,
                "platform_ma_rising": False,
                "macd_dif": 0.08,
                "macd_dea": -0.01,
                "is_st": False,
                "suspended": False,
            },
            {
                "code": "600000.SH",
                "name": "浦发银行",
                "latest_price": 8.0,
                "amount": 30_000_000,
                "float_market_value": 80_000_000_000,
                "ma_short": 8.2,
                "ma_long": 8.1,
                "rps20": 90.0,
                "turnover_rate": 3.0,
                "pct_chg": 6.0,
                "amplitude": 0.09,
                "volume_ratio": 2.6,
                "ma_distance": 0.02,
                "platform_ready": True,
                "platform_range": 0.07,
                "platform_bullish_ratio": 0.65,
                "platform_bull_volume_ratio": 1.3,
                "platform_breakout_volume_ratio": 3.0,
                "platform_breakout_bullish": True,
                "platform_breakout_pct_chg": 6.0,
                "platform_body_strength": 1.4,
                "platform_ma_bullish": True,
                "platform_ma_rising": True,
                "macd_dif": 0.2,
                "macd_dea": 0.1,
                "is_st": False,
                "suspended": False,
            },
        ]
    )
    config = {
        **DEFAULT_STRATEGY_CONFIG,
        "analysis_mode": "score",
        "signal_mode": "platform_breakout",
        "min_price": 5,
        "min_amount": 100_000_000,
        "min_rps20": 70,
        "platform_max_range": 0.08,
        "platform_min_bullish_ratio": 0.55,
        "platform_breakout_volume_ratio": 2.5,
        "platform_breakout_pct_chg_min": 5,
        "candidate_limit": 10,
    }

    candidates, funnel, zero_reason = apply_strategy_filters(rows, config)

    assert [row["code"] for row in candidates] == ["000001.SZ"]
    assert candidates[0]["signal_type"] == "平台突破观察"
    assert any("综合评分" in reason for reason in candidates[0]["reasons"])
    assert "平台振幅" not in [step["step_name"] for step in funnel]
    assert any(step["step_name"] == "综合评分" for step in funnel)
    assert zero_reason is None
