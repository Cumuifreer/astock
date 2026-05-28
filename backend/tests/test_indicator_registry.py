from backend.app.services.indicator_registry import indicator_library
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

    assert indicators["rps120"]["paired_strategy_ids"] == ["min_rps120"]
    assert indicators["volume_ratio"]["paired_strategy_ids"] == ["volume_ratio_min", "platform_breakout_volume_ratio"]
    assert indicators["topic_count"]["paired_strategy_ids"] == ["min_topic_count"]
    assert indicators["topic_heat"]["paired_strategy_ids"] == ["min_topic_heat"]
    assert indicators["theme_limit_count"]["paired_strategy_ids"] == ["min_theme_limit_count"]
    assert {"min_topic_count", "min_topic_heat", "min_theme_limit_count"}.issubset(set(indicators))
    assert indicators["topic_heat"]["data_status"] == "executable"
    assert indicators["theme_limit_count"]["data_status"] == "executable"


def test_indicator_library_no_longer_exposes_signal_mode_templates_or_interactions():
    library = indicator_library()

    assert library["signal_modes"] == []
    assert library["summary"]["signal_mode_count"] == 0
    assert library["summary"]["interaction_rule_count"] == 0
    assert all("interaction" not in (indicator.get("usage") or []) for indicator in library["indicators"])


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
    assert set(DEFAULT_STRATEGY_CONFIG) - strategy_keys == {
        "analysis_mode",
        "analysis_engines",
        "signal_mode",
        "macd_filter_enabled",
        "strategy_rules",
        "strategy_interactions",
        "strategy_resonances",
        "resonance_bonus_cap",
    }
    assert all(key in DEFAULT_STRATEGY_CONFIG for key in strategy_keys if key)
    assert all(indicator.get("control", {}).get("type") for indicator in indicators.values() if indicator.get("kind") == "strategy_param")


def test_strategy_parameter_profile_can_be_built_from_indicator_library():
    library = indicator_library()
    indicator_ids = {indicator["id"] for indicator in library["indicators"]}
    strategy_param_ids = [indicator["id"] for indicator in library["indicators"] if indicator["kind"] == "strategy_param"]

    assert {"min_price", "min_amount", "candidate_limit", "sort_by"}.issubset(set(strategy_param_ids))
    assert set(strategy_param_ids).issubset(indicator_ids)


def test_indicator_library_exposes_rule_builder_metadata():
    library = indicator_library()
    indicators = {indicator["id"]: indicator for indicator in library["indicators"]}

    amount = indicators["amount"]
    assert amount["value_type"] == "money"
    assert amount["unit"] == "元"
    assert amount["analysis_field"] == "amount"
    assert "filter" in amount["supported_actions"]
    assert "score" in amount["supported_actions"]
    assert amount["hard_filter_allowed"] is True
    assert amount["operator_semantics"] == "numeric"
    assert {"gte", "lte", "between"}.issubset(set(amount["supported_operators"]))
    assert amount["default_operator"] == "gte"
    assert amount["data_status"] == "executable"
    assert amount["recommended_rules"]

    topic_heat = indicators["topic_heat"]
    assert topic_heat["value_type"] == "score"
    assert topic_heat["unit"] == "分"
    assert topic_heat["range_hint"] == {"min": 0, "max": 100}
    assert topic_heat["direction"] == "higher_better"

    top_list = indicators["top_list_net_amount"]
    assert top_list["data_status"] == "executable"
    assert "filter" not in top_list["supported_actions"]
    assert {"score", "risk", "display"}.issubset(set(top_list["supported_actions"]))
    assert top_list["hard_filter_allowed"] is False
    assert top_list["display_scope"] == "candidate"

    min_price = indicators["min_price"]
    assert min_price["value_type"] == "number"
    assert min_price["supported_actions"] == []


def test_indicator_contract_does_not_overstate_executable_actions():
    library = indicator_library()
    indicators = {indicator["id"]: indicator for indicator in library["indicators"]}

    moneyflow = indicators["main_net_amount"]
    assert moneyflow["data_status"] == "executable"
    assert moneyflow["supported_actions"] == ["score", "display"]
    assert moneyflow["hard_filter_allowed"] is False

    cost = indicators["cost_50pct"]
    assert cost["data_status"] == "executable"
    assert cost["supported_actions"] == ["display"]
    assert cost["hard_filter_allowed"] is False
    assert cost["display_scope"] == "candidate"

    price_to_cost = indicators["price_to_cost_50pct"]
    assert price_to_cost["value_type"] == "ratio"
    assert price_to_cost["unit"] == "比例"
    assert price_to_cost["default_operator"] == "between"
    assert price_to_cost["supported_actions"] == ["score", "risk", "display"]

    limit_event = indicators["limit_event"]
    assert limit_event["analysis_field"] == "limit_type"
    assert limit_event["operator_semantics"] == "event_state"
    assert limit_event["supported_operators"] == ["eq", "neq"]
    assert limit_event["default_operator"] == "eq"
    assert limit_event["choice_options"] == [
        {"value": "U", "label": "涨停"},
        {"value": "Z", "label": "炸板"},
        {"value": "D", "label": "跌停"},
    ]
    assert {rule["label"] for rule in limit_event["recommended_rules"]} >= {"今日涨停", "今日炸板风险", "今日跌停风险"}

    overheat = indicators["overheat_risk"]
    assert overheat["data_status"] == "display_only"
    assert overheat["supported_actions"] == ["display"]
    assert overheat["display_scope"] == "planned"

    macd_state = indicators["macd_state"]
    assert macd_state["data_status"] == "display_only"
    assert macd_state["supported_actions"] == ["display"]
    assert macd_state["display_scope"] == "planned"

    market = indicators["market_breadth"]
    assert market["data_status"] == "display_only"
    assert market["supported_actions"] == ["display"]
    assert market["operator_semantics"] == "market_context"
