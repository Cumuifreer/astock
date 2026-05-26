from backend.app.services.indicator_registry import indicator_library


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


def test_signal_mode_templates_include_editable_interaction_rules():
    library = indicator_library()
    templates = {template["id"]: template for template in library["signal_modes"]}

    template = templates["theme_resonance_breakout"]
    interactions = [rule for group in template["rule_groups"] for rule in group["rules"] if rule["kind"] == "interaction"]

    assert template["base_signal_mode"] == "platform_breakout"
    assert interactions
    assert interactions[0]["editable"] is True
    assert {"platform_breakout_clearance", "volume_ratio", "topic_heat"}.issubset(set(interactions[0]["indicator_ids"]))
    assert interactions[0]["effect"]["type"] == "score"
