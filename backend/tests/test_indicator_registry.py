from backend.app.services.indicator_registry import blank_signal_mode, indicator_library
from backend.app.services.strategy_service import DEFAULT_STRATEGY_CONFIG


def test_indicator_library_groups_a_share_indicators_by_domain():
    library = indicator_library()

    category_ids = {category["id"] for category in library["categories"]}
    indicator_ids = {indicator["id"] for indicator in library["indicators"]}

    assert {"quote", "technical", "capital_flow", "theme", "event", "chips", "risk"}.issubset(category_ids)
    assert {
        "volume_ratio",
        "rps20",
        "topic_heat",
        "main_net_amount",
        "limit_event",
        "cyq_winner_rate",
    }.issubset(indicator_ids)
    assert all(indicator["category_id"] in category_ids for indicator in library["indicators"])
    assert all(indicator["formula"] for indicator in library["indicators"])


def test_observation_indicators_point_to_editable_strategy_params():
    library = indicator_library()
    indicators = {indicator["id"]: indicator for indicator in library["indicators"]}
    theme_mode = next(mode for mode in library["signal_modes"] if mode["id"] == "theme_resonance_breakout")
    theme_fields = {field["indicator_id"] for field in theme_mode["fields"]}

    assert indicators["rps120"]["paired_strategy_ids"] == ["min_rps120"]
    assert indicators["volume_ratio"]["paired_strategy_ids"] == ["volume_ratio_min", "platform_breakout_volume_ratio"]
    assert indicators["topic_count"]["paired_strategy_ids"] == ["min_topic_count"]
    assert indicators["topic_heat"]["paired_strategy_ids"] == ["min_topic_heat"]
    assert indicators["theme_limit_count"]["paired_strategy_ids"] == ["min_theme_limit_count"]
    assert {"min_topic_count", "min_topic_heat", "min_theme_limit_count"}.issubset(set(indicators))
    assert {"topic_heat", "theme_limit_count", "min_topic_heat", "min_theme_limit_count"}.issubset(theme_fields)


def test_existing_theme_mode_is_extended_with_new_theme_parameters():
    library = indicator_library(
        [
            {
                "id": "theme_resonance_breakout",
                "name": "题材共振突破",
                "description": "",
                "note": "",
                "runtime_signal_mode": "platform_breakout",
                "fields": [
                    {"indicator_id": "topic_heat", "role": "score"},
                    {"indicator_id": "theme_limit_count", "role": "score"},
                ],
                "rule_groups": [],
            }
        ]
    )
    fields = {field["indicator_id"]: field["role"] for field in library["signal_modes"][0]["fields"]}

    assert fields["min_topic_count"] == "filter"
    assert fields["min_topic_heat"] == "score"
    assert fields["min_theme_limit_count"] == "score"
    assert fields["topic_count"] == "display"


def test_signal_mode_templates_include_editable_interaction_rules():
    library = indicator_library()
    templates = {template["id"]: template for template in library["signal_modes"]}

    template = templates["theme_resonance_breakout"]
    interactions = [rule for group in template["rule_groups"] for rule in group["rules"] if rule["kind"] == "interaction"]

    assert "base_signal_mode" not in template
    assert interactions
    assert interactions[0]["editable"] is True
    assert {"platform_breakout_clearance", "volume_ratio", "topic_heat"}.issubset(set(interactions[0]["indicator_ids"]))
    assert interactions[0]["effect"]["type"] == "score"


def test_all_strategy_form_fields_are_defined_in_indicator_library():
    library = indicator_library()
    indicators = {indicator["id"]: indicator for indicator in library["indicators"]}
    strategy_keys = {
        indicator.get("strategy_key")
        for indicator in indicators.values()
        if indicator.get("kind") == "strategy_param"
    }

    required_keys = {
        "min_price",
        "min_amount",
        "min_float_market_value",
        "max_float_market_value",
        "include_bj",
        "exclude_star_board",
        "breakout_pullback_direction",
        "pullback_tolerance",
        "platform_lookback_days",
        "platform_range_basis",
        "platform_max_range_mode",
        "platform_max_range",
        "platform_min_bullish_ratio",
        "platform_bull_volume_advantage",
        "platform_breakout_require_close_above",
        "platform_breakout_clearance",
        "platform_breakout_volume_ratio",
        "platform_breakout_pct_chg_min",
        "platform_body_strength_min",
        "platform_setup_lookback_days",
        "platform_setup_max_distance_to_high",
        "trend_ema_fast_window",
        "trend_macd_mode",
        "trend_stoch_mode",
        "ma_short_window",
        "ma_long_window",
        "rps_window",
        "min_rps20",
        "max_turnover",
        "volume_ratio_min",
        "sort_by",
        "missing_turnover_policy",
        "missing_float_market_value_policy",
    }

    assert required_keys.issubset(strategy_keys)
    assert set(DEFAULT_STRATEGY_CONFIG) - strategy_keys == {"analysis_mode", "signal_mode"}
    assert all(key in DEFAULT_STRATEGY_CONFIG for key in strategy_keys if key)
    assert all(indicator.get("control", {}).get("type") for indicator in indicators.values() if indicator.get("kind") == "strategy_param")


def test_signal_modes_reference_existing_indicators_and_new_mode_starts_with_stock_pool_only():
    library = indicator_library()
    indicator_ids = {indicator["id"] for indicator in library["indicators"]}

    for mode in library["signal_modes"]:
        assert "base_signal_mode" not in mode
        assert mode["fields"]
        assert all(field["indicator_id"] in indicator_ids for field in mode["fields"])
        for group in mode["rule_groups"]:
            for rule in group["rules"]:
                assert all(indicator_id in indicator_ids for indicator_id in rule["indicator_ids"])

    blank = blank_signal_mode("我的信号模式")
    assert blank["name"] == "我的信号模式"
    assert [field["indicator_id"] for field in blank["fields"]] == [
        "min_price",
        "min_amount",
        "min_float_market_value",
        "max_float_market_value",
        "include_bj",
        "exclude_star_board",
        "missing_turnover_policy",
        "missing_float_market_value_policy",
    ]
    assert blank["rule_groups"] == []
