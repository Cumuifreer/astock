from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional


INDICATOR_CATEGORIES: List[Dict[str, str]] = [
    {"id": "stock_pool", "label": "基础股票池", "description": "价格、成交、市值、市场范围和缺失数据处理。"},
    {"id": "quote", "label": "基础行情", "description": "价格、成交、换手、量比和市值等行情字段。"},
    {"id": "technical", "label": "技术强弱", "description": "RPS、均线、MACD、KDJ、平台形态等本地 K 线指标。"},
    {"id": "platform", "label": "平台形态", "description": "平台突破、平台临界、区间收敛和突破确认参数。"},
    {"id": "trend", "label": "趋势共振", "description": "EMA、MACD、随机指标和趋势过热参数。"},
    {"id": "capital_flow", "label": "资金流向", "description": "主力净额、净流入和大小单结构。"},
    {"id": "theme", "label": "题材行业", "description": "同花顺概念/行业成分以及题材热度。"},
    {"id": "event", "label": "事件异动", "description": "涨跌停、炸板、龙虎榜和游资等高信息密度事件。"},
    {"id": "chips", "label": "筹码成本", "description": "筹码胜率、成本分布和潜在抛压。"},
    {"id": "risk", "label": "风险过滤", "description": "ST、停牌、涨幅过热、换手过热和异常事件风险。"},
    {"id": "market", "label": "市场环境", "description": "市场宽度、指数趋势和涨跌停温度。"},
]

RULE_ACTIONS = {"filter", "score", "risk", "display"}
NUMERIC_OPERATORS = ["gte", "lte", "gt", "lt", "between", "eq", "neq"]
BOOLEAN_OPERATORS = ["is_true", "eq", "neq"]
CHOICE_OPERATORS = ["eq", "neq"]
EVENT_OPERATORS = ["recent", "eq", "neq"]
EVENT_STATE_OPERATORS = ["eq", "neq"]

RULE_META_BY_ID: Dict[str, Dict[str, Any]] = {
    "latest_price": {
        "value_type": "money",
        "unit": "元",
        "direction": "range_better",
        "recommended_rules": [
            {"label": "剔除低价股", "action": "filter", "operator": "gte", "value": 4},
        ],
    },
    "amount": {
        "value_type": "money",
        "unit": "元",
        "direction": "higher_better",
        "recommended_rules": [
            {"label": "流动性 8000万+", "action": "filter", "operator": "gte", "value": 80_000_000},
            {"label": "强成交 2亿+", "action": "score", "operator": "gte", "value": 200_000_000, "weight": 8},
        ],
    },
    "turnover_rate": {
        "value_type": "percent",
        "unit": "%",
        "direction": "range_better",
        "recommended_rules": [
            {"label": "活跃 1%+", "action": "filter", "operator": "gte", "value": 1},
            {"label": "换手过热", "action": "risk", "operator": "gte", "value": 12, "weight": 8},
        ],
    },
    "volume_ratio": {
        "value_type": "multiple",
        "unit": "倍",
        "direction": "higher_better",
        "recommended_rules": [
            {"label": "温和放量", "action": "filter", "operator": "gte", "value": 1.1},
            {"label": "突破放量", "action": "score", "operator": "gte", "value": 2.5, "weight": 10},
        ],
    },
    "float_market_value": {
        "value_type": "money",
        "unit": "元",
        "direction": "range_better",
        "recommended_rules": [
            {"label": "20亿以上", "action": "filter", "operator": "gte", "value": 2_000_000_000},
            {"label": "500亿以下", "action": "filter", "operator": "lte", "value": 50_000_000_000},
        ],
    },
    "topic_count": {"value_type": "number", "unit": "个", "direction": "higher_better"},
    "topic_heat": {
        "value_type": "score",
        "unit": "分",
        "range_hint": {"min": 0, "max": 100},
        "direction": "higher_better",
        "recommended_rules": [
            {"label": "主线热度 60+", "action": "score", "operator": "gte", "value": 60, "weight": 8},
            {"label": "强主线 75+", "action": "filter", "operator": "gte", "value": 75},
        ],
    },
    "theme_limit_count": {"value_type": "number", "unit": "只", "direction": "higher_better"},
    "limit_event": {
        "value_type": "event",
        "unit": "事件",
        "direction": "event",
        "operator_semantics": "event_state",
        "supported_operators": EVENT_STATE_OPERATORS,
        "default_operator": "eq",
        "hard_filter_allowed": False,
        "choice_options": [
            {"value": "U", "label": "涨停"},
            {"value": "Z", "label": "炸板"},
            {"value": "D", "label": "跌停"},
        ],
        "recommended_rules": [
            {"label": "今日涨停", "action": "score", "operator": "eq", "value": "U", "weight": 8},
            {"label": "今日炸板风险", "action": "risk", "operator": "eq", "value": "Z", "weight": 8},
            {"label": "今日跌停风险", "action": "risk", "operator": "eq", "value": "D", "weight": 15},
        ],
    },
    "limit_fd_mv_ratio": {"value_type": "ratio", "unit": "比例", "direction": "higher_better", "hard_filter_allowed": False},
    "top_list_net_amount": {"value_type": "money", "unit": "元", "direction": "higher_better"},
    "top_inst_net_buy": {"value_type": "money", "unit": "元", "direction": "higher_better", "hard_filter_allowed": False},
    "hot_money_net_amount": {"value_type": "money", "unit": "元", "direction": "higher_better", "hard_filter_allowed": False},
    "main_net_amount": {"value_type": "money", "unit": "元", "direction": "higher_better"},
    "net_mf_amount": {"value_type": "money", "unit": "元", "direction": "higher_better"},
    "cyq_winner_rate": {"value_type": "percent", "unit": "%", "direction": "range_better"},
    "cost_50pct": {"value_type": "money", "unit": "元", "direction": "neutral", "hard_filter_allowed": False},
    "price_to_cost_50pct": {
        "value_type": "ratio",
        "unit": "比例",
        "direction": "range_better",
        "default_operator": "between",
        "hard_filter_allowed": False,
        "recommended_rules": [
            {"label": "贴近成本中枢", "action": "score", "operator": "between", "value": -0.05, "value2": 0.15, "weight": 6},
            {"label": "成本偏离过热", "action": "risk", "operator": "gte", "value": 0.3, "weight": 8},
        ],
    },
    "is_st": {"value_type": "boolean", "unit": "", "direction": "lower_better", "default_operator": "is_true"},
    "market_breadth": {
        "value_type": "score",
        "unit": "分",
        "range_hint": {"min": 0, "max": 100},
        "direction": "higher_better",
        "operator_semantics": "market_context",
        "hard_filter_allowed": False,
    },
}


def _default_value_type(indicator_id: str, category_id: str) -> str:
    if indicator_id.startswith("rps") or indicator_id.endswith("_heat"):
        return "score"
    if "amount" in indicator_id or "market_value" in indicator_id or indicator_id.startswith("cost_"):
        return "money"
    if any(token in indicator_id for token in ("ratio", "range", "clearance", "distance", "amplitude", "gain")):
        return "ratio"
    if category_id == "event":
        return "event"
    if indicator_id.startswith("is_") or indicator_id.endswith("_required"):
        return "boolean"
    return "number"


def _default_unit(value_type: str) -> str:
    return {
        "money": "元",
        "percent": "%",
        "ratio": "比例",
        "multiple": "倍",
        "score": "分",
        "event": "事件",
        "boolean": "",
    }.get(value_type, "")


def _default_operators(value_type: str) -> List[str]:
    if value_type == "boolean":
        return BOOLEAN_OPERATORS
    if value_type == "event":
        return EVENT_OPERATORS
    if value_type == "choice":
        return CHOICE_OPERATORS
    return NUMERIC_OPERATORS


def _operator_semantics(value_type: str) -> str:
    if value_type == "boolean":
        return "boolean"
    if value_type == "choice":
        return "choice"
    if value_type == "event":
        return "event_state"
    return "numeric"


def _default_operator(value_type: str, direction: str) -> str:
    if value_type == "boolean":
        return "is_true"
    if value_type == "event":
        return "recent"
    if direction == "lower_better":
        return "lte"
    if direction == "range_better":
        return "between"
    return "gte"


def _rule_builder_meta(
    indicator_id: str,
    category_id: str,
    usage: List[str],
    *,
    status: str,
    analysis_ready: bool,
    kind: str,
    control: Optional[Dict[str, Any]] = None,
    analysis_field: Optional[str] = None,
    value_type: Optional[str] = None,
    unit: Optional[str] = None,
    range_hint: Optional[Dict[str, Any]] = None,
    direction: Optional[str] = None,
    supported_actions: Optional[List[str]] = None,
    supported_operators: Optional[List[str]] = None,
    default_operator: Optional[str] = None,
    recommended_rules: Optional[List[Dict[str, Any]]] = None,
    hard_filter_allowed: Optional[bool] = None,
    min_coverage_for_filter: Optional[float] = None,
    freshness_required: Optional[bool] = None,
    coverage_group: Optional[str] = None,
    operator_semantics: Optional[str] = None,
) -> Dict[str, Any]:
    configured = RULE_META_BY_ID.get(indicator_id, {})
    if kind == "strategy_param":
        inferred_type = (control or {}).get("type") or "number"
        if inferred_type == "money":
            inferred_type = "money"
        elif inferred_type == "boolean":
            inferred_type = "boolean"
        elif inferred_type == "select":
            inferred_type = "choice"
        else:
            inferred_type = "number"
        resolved_type = str(value_type or configured.get("value_type") or inferred_type)
        return {
            "value_type": resolved_type,
            "unit": unit if unit is not None else str(configured.get("unit") or (control or {}).get("unit") or _default_unit(resolved_type)),
            "range_hint": range_hint if range_hint is not None else configured.get("range_hint"),
            "direction": direction or str(configured.get("direction") or "neutral"),
            "supported_actions": [],
            "supported_operators": supported_operators or _default_operators(resolved_type),
            "default_operator": default_operator or str(configured.get("default_operator") or _default_operator(resolved_type, "neutral")),
            "recommended_rules": recommended_rules or configured.get("recommended_rules") or [],
            "analysis_field": analysis_field or configured.get("analysis_field") or None,
            "data_status": "parameter",
            "hard_filter_allowed": False,
            "min_coverage_for_filter": min_coverage_for_filter if min_coverage_for_filter is not None else configured.get("min_coverage_for_filter"),
            "freshness_required": freshness_required if freshness_required is not None else bool(configured.get("freshness_required", False)),
            "coverage_group": coverage_group or configured.get("coverage_group"),
            "operator_semantics": operator_semantics or str(configured.get("operator_semantics") or _operator_semantics(resolved_type)),
            "choice_options": configured.get("choice_options") or [],
            "display_scope": configured.get("display_scope"),
        }

    resolved_type = str(value_type or configured.get("value_type") or _default_value_type(indicator_id, category_id))
    resolved_direction = direction or str(configured.get("direction") or "higher_better")
    resolved_semantics = operator_semantics or str(configured.get("operator_semantics") or _operator_semantics(resolved_type))
    if status == "planned":
        actions: List[str] = []
        data_status = "planned"
    elif not analysis_ready:
        actions = ["display"]
        data_status = "display_only"
    else:
        usage_actions = [item for item in usage if item in RULE_ACTIONS]
        actions = list(dict.fromkeys(supported_actions or usage_actions or ["display"]))
        if "display" not in actions:
            actions.append("display")
        data_status = "executable"
    configured_hard_filter = configured.get("hard_filter_allowed")
    can_hard_filter = (
        bool(hard_filter_allowed)
        if hard_filter_allowed is not None
        else bool(configured_hard_filter)
        if configured_hard_filter is not None
        else "filter" in actions
    )
    if not can_hard_filter and "filter" in actions:
        actions = [action for action in actions if action != "filter"]
    display_scope = configured.get("display_scope")
    if display_scope is None:
        display_scope = "candidate" if data_status == "executable" and "display" in actions else "planned" if data_status == "display_only" else None
    return {
        "value_type": resolved_type,
        "unit": unit if unit is not None else str(configured.get("unit") or _default_unit(resolved_type)),
        "range_hint": range_hint if range_hint is not None else configured.get("range_hint"),
        "direction": resolved_direction,
        "supported_actions": actions,
        "supported_operators": supported_operators or configured.get("supported_operators") or _default_operators(resolved_type),
        "default_operator": default_operator or str(configured.get("default_operator") or _default_operator(resolved_type, resolved_direction)),
        "recommended_rules": recommended_rules or configured.get("recommended_rules") or [],
        "analysis_field": analysis_field or configured.get("analysis_field") or indicator_id,
        "data_status": data_status,
        "hard_filter_allowed": can_hard_filter,
        "min_coverage_for_filter": min_coverage_for_filter if min_coverage_for_filter is not None else configured.get("min_coverage_for_filter"),
        "freshness_required": freshness_required if freshness_required is not None else bool(configured.get("freshness_required", False)),
        "coverage_group": coverage_group or configured.get("coverage_group"),
        "operator_semantics": resolved_semantics,
        "choice_options": configured.get("choice_options") or [],
        "display_scope": display_scope,
    }


def data_indicator(
    indicator_id: str,
    name: str,
    category_id: str,
    source: str,
    formula: str,
    description: str,
    usage: List[str],
    *,
    status: str = "active",
    missing: str = "neutral",
    analysis_ready: bool = True,
    paired_strategy_ids: Optional[List[str]] = None,
    analysis_field: Optional[str] = None,
    value_type: Optional[str] = None,
    unit: Optional[str] = None,
    range_hint: Optional[Dict[str, Any]] = None,
    direction: Optional[str] = None,
    supported_actions: Optional[List[str]] = None,
    supported_operators: Optional[List[str]] = None,
    default_operator: Optional[str] = None,
    recommended_rules: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    control = {"type": "readonly"}
    return {
        "id": indicator_id,
        "name": name,
        "category_id": category_id,
        "kind": "data",
        "status": status,
        "source": source,
        "formula": formula,
        "description": description,
        "usage": usage,
        "default_missing_policy": missing,
        "analysis_ready": analysis_ready,
        "paired_strategy_ids": paired_strategy_ids or [],
        "control": control,
        "group_id": category_id,
        "group_label": next((item["label"] for item in INDICATOR_CATEGORIES if item["id"] == category_id), category_id),
        **_rule_builder_meta(
            indicator_id,
            category_id,
            usage,
            status=status,
            analysis_ready=analysis_ready,
            kind="data",
            control=control,
            analysis_field=analysis_field,
            value_type=value_type,
            unit=unit,
            range_hint=range_hint,
            direction=direction,
            supported_actions=supported_actions,
            supported_operators=supported_operators,
            default_operator=default_operator,
            recommended_rules=recommended_rules,
        ),
    }


def strategy_param(
    key: str,
    name: str,
    category_id: str,
    group_id: str,
    group_label: str,
    control: Dict[str, Any],
    description: str,
    *,
    formula: Optional[str] = None,
    usage: Optional[List[str]] = None,
    missing: str = "allow",
) -> Dict[str, Any]:
    resolved_usage = usage or ["filter"]
    return {
        "id": key,
        "name": name,
        "category_id": category_id,
        "kind": "strategy_param",
        "strategy_key": key,
        "status": "active",
        "source": "策略配置",
        "formula": formula or "由用户在策略参数中设置，分析运行时读取该参数。",
        "description": description,
        "usage": resolved_usage,
        "default_missing_policy": missing,
        "analysis_ready": True,
        "control": control,
        "group_id": group_id,
        "group_label": group_label,
        **_rule_builder_meta(
            key,
            category_id,
            resolved_usage,
            status="active",
            analysis_ready=True,
            kind="strategy_param",
            control=control,
            analysis_field=None,
        ),
    }


def number_control(
    *,
    unit: str = "",
    allow_blank: bool = False,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    step: Optional[float] = None,
) -> Dict[str, Any]:
    control: Dict[str, Any] = {"type": "number", "unit": unit, "allow_blank": allow_blank}
    if min_value is not None:
        control["min"] = min_value
    if max_value is not None:
        control["max"] = max_value
    if step is not None:
        control["step"] = step
    return control


def money_control(*, allow_blank: bool = False) -> Dict[str, Any]:
    return {"type": "money", "unit": "元", "allow_blank": allow_blank}


def select_control(options: Iterable[tuple[str, str]]) -> Dict[str, Any]:
    return {"type": "select", "options": [{"value": value, "label": label} for value, label in options]}


def boolean_control() -> Dict[str, Any]:
    return {"type": "boolean"}


CONDITION_OPTIONS = [("must", "必须满足"), ("score", "只参与得分"), ("off", "不启用")]


DATA_INDICATORS: List[Dict[str, Any]] = [
    data_indicator(
        "latest_price",
        "最新价",
        "quote",
        "Tushare 实时日线 / 本地历史 K 线",
        "优先取当日行情快照 latest_price，缺失时取最新历史 K 线 close。",
        "用于过滤过低价格和展示当前交易位置。",
        ["filter", "display"],
        missing="skip",
        paired_strategy_ids=["min_price"],
    ),
    data_indicator(
        "amount",
        "成交额",
        "quote",
        "Tushare 实时日线 / 历史 K 线",
        "当日快照 amount，缺失时取最新历史 K 线 amount。",
        "衡量流动性，低成交额股票容易滑点大、信号失真。",
        ["filter", "score"],
        missing="skip",
        paired_strategy_ids=["min_amount"],
    ),
    data_indicator(
        "turnover_rate",
        "换手率",
        "quote",
        "Tushare daily_basic / 历史 K 线",
        "优先取 daily_basic.turnover_rate，缺失时取历史 K 线 turn。",
        "衡量筹码交换强度，过低代表不活跃，过高可能代表分歧或过热。",
        ["filter", "risk", "score"],
        missing="allow",
        paired_strategy_ids=["min_turnover", "max_turnover"],
    ),
    data_indicator(
        "volume_ratio",
        "量比",
        "quote",
        "Tushare daily_basic / 本地 K 线估算",
        "优先取 daily_basic.volume_ratio；为空时用最新成交量 / 前 20 根成交量均值。",
        "判断当前成交是否明显放大，是右侧突破和资金确认的重要指标。",
        ["filter", "score"],
        missing="allow",
        paired_strategy_ids=["volume_ratio_min", "platform_breakout_volume_ratio"],
    ),
    data_indicator(
        "float_market_value",
        "流通市值",
        "quote",
        "Tushare daily_basic / 快照估算",
        "优先使用 daily_basic.circ_mv 归一化后的流通市值，缺失时由流通股本和价格估算。",
        "控制股票规模，避免过小或过大的标的进入同一套策略。",
        ["filter"],
        missing="allow",
        paired_strategy_ids=["min_float_market_value", "max_float_market_value"],
    ),
    data_indicator("rps20", "RPS20", "technical", "本地历史 K 线", "按最近 20 日收益率在全市场排序并映射到 0-100。", "短期相对强度。", ["filter", "score", "sort"], missing="skip", paired_strategy_ids=["min_rps20"]),
    data_indicator("rps60", "RPS60", "technical", "本地历史 K 线", "按最近 60 日收益率在全市场排序并映射到 0-100。", "中期相对强度。", ["filter", "score", "sort"], missing="skip", paired_strategy_ids=["min_rps60"]),
    data_indicator("rps120", "RPS120", "technical", "本地历史 K 线", "按最近 120 日收益率在全市场排序并映射到 0-100。", "中长期相对强度。", ["filter", "score", "sort"], missing="skip", paired_strategy_ids=["min_rps120"]),
    data_indicator("macd_state", "MACD 状态", "technical", "本地历史 K 线 / Tushare stk_factor", "DIF、DEA 和 0 轴关系。", "确认动能是否改善。", ["display"], missing="allow", analysis_ready=False),
    data_indicator("platform_range", "平台振幅", "platform", "本地历史 K 线", "平台窗口内最高价 / 最低价 - 1，或按收盘价区间计算。", "衡量横盘收敛程度。", ["filter", "score"], missing="skip", paired_strategy_ids=["platform_max_range", "platform_max_range_mode"]),
    data_indicator("platform_breakout_clearance", "突破上沿距离", "platform", "本地历史 K 线", "最新收盘价 / 平台上沿 - 1。", "判断是否刚刚有效站上平台上沿。", ["filter", "score"], missing="skip", paired_strategy_ids=["platform_breakout_clearance", "platform_breakout_max_clearance"]),
    data_indicator("platform_setup_distance_to_high", "距平台上沿", "platform", "本地历史 K 线", "平台上沿 / 最新收盘价 - 1。", "平台临界模式的核心位置指标。", ["filter", "score"], missing="skip", paired_strategy_ids=["platform_setup_max_distance_to_high"]),
    data_indicator("main_net_amount", "主力净额", "capital_flow", "Tushare moneyflow", "大单与超大单买入金额 - 卖出金额。", "判断主动资金是否回流。", ["score", "display"], status="active", analysis_ready=True),
    data_indicator("net_mf_amount", "资金净流入", "capital_flow", "Tushare moneyflow", "全口径买入金额 - 卖出金额。", "辅助确认资金方向。", ["score", "display"], status="active", analysis_ready=True),
    data_indicator("large_net_amount", "大单净额", "capital_flow", "Tushare moneyflow", "大单买入金额 - 大单卖出金额。", "观察大单资金方向。", ["score", "display"], status="active", analysis_ready=True),
    data_indicator("super_large_net_amount", "超大单净额", "capital_flow", "Tushare moneyflow", "超大单买入金额 - 超大单卖出金额。", "观察强资金方向。", ["score", "display"], status="active", analysis_ready=True),
    data_indicator("topic_count", "题材数", "theme", "Tushare ths_member", "统计股票关联的同花顺概念/行业成分数量。", "表示股票挂在哪些题材里。", ["display", "score"], status="active", analysis_ready=True, paired_strategy_ids=["min_topic_count"]),
    data_indicator("topic_heat", "题材热度", "theme", "ths_member + 当日行情 + 涨跌停", "成分股上涨比例、RPS 高分股数量、涨停数量和成交额扩张综合评分。", "判断个股是否站在活跃主线上。", ["score", "sort"], status="active", analysis_ready=True, paired_strategy_ids=["min_topic_heat"]),
    data_indicator("theme_limit_count", "题材涨停数", "theme", "ths_member + Tushare limit_list_d", "统计股票所属题材内最近交易日涨停成分股数量。", "衡量题材短线爆发力。", ["score"], status="active", analysis_ready=True, paired_strategy_ids=["min_theme_limit_count"]),
    data_indicator("limit_event", "涨跌停 / 炸板", "event", "Tushare limit_list_d", "读取最近涨停、跌停或炸板事件及开板次数、封单金额。", "低覆盖事件指标。", ["risk", "score", "display"], status="active", analysis_ready=True, analysis_field="limit_type"),
    data_indicator("limit_fd_mv_ratio", "封单市值比", "event", "Tushare limit_list_d", "封单金额 / 流通市值。", "判断涨停封单强度。", ["score", "display"], status="active", analysis_ready=True),
    data_indicator("top_list_net_amount", "龙虎榜净额", "event", "Tushare top_list / top_inst / hm_detail", "取最近龙虎榜净买入金额。", "短线资金偏好指标。", ["score", "risk", "display"], status="active", analysis_ready=True),
    data_indicator("top_inst_net_buy", "机构净买额", "event", "Tushare top_inst", "机构席位净买入金额合计。", "观察机构席位方向。", ["score", "display"], status="active", analysis_ready=True),
    data_indicator("hot_money_net_amount", "游资净买额", "event", "Tushare hm_detail", "游资席位净买入金额合计。", "观察游资方向。", ["score", "display"], status="active", analysis_ready=True),
    data_indicator("cyq_winner_rate", "筹码胜率", "chips", "Tushare cyq_perf", "获利筹码占比。", "观察筹码位置与潜在抛压。", ["score", "risk"], status="active", analysis_ready=True),
    data_indicator("cost_50pct", "中位成本", "chips", "Tushare cyq_perf", "筹码分布中 50% 成本位置。", "观察当前价和中位成本的距离。", ["display"], status="active", analysis_ready=True),
    data_indicator("price_to_cost_50pct", "距中位成本", "chips", "Tushare cyq_perf", "当前价 / 中位成本 - 1。", "衡量当前价相对筹码中枢的位置。", ["score", "risk", "display"], status="active", analysis_ready=True),
    data_indicator("is_st", "ST 状态", "risk", "股票基础信息 / 历史 K 线", "股票名或历史数据中的 ST 标记。", "默认风险过滤项。", ["filter", "risk"], missing="allow"),
    data_indicator("overheat_risk", "过热风险", "risk", "本地计算", "近 5/10 日涨幅、当前涨幅、换手率和距均线偏离度。", "识别脱离买点或分歧过大的候选股。", ["display"], analysis_ready=False),
    data_indicator("market_breadth", "市场宽度", "market", "本地历史 K 线 / 市场环境表", "全市场上涨比例、涨跌停温度和指数趋势综合评分。", "判断策略环境是否顺风。", ["context", "risk"], status="available", analysis_ready=False),
]


STRATEGY_PARAM_INDICATORS: List[Dict[str, Any]] = [
    strategy_param("min_price", "最低股价", "stock_pool", "stock_pool", "基础股票池", number_control(unit="元", min_value=0), "低于该价格的股票不进入候选。"),
    strategy_param("min_amount", "成交额门槛", "stock_pool", "stock_pool", "基础股票池", money_control(), "低成交额股票会被过滤。"),
    strategy_param("min_float_market_value", "最小流通市值", "stock_pool", "stock_pool", "基础股票池", money_control(allow_blank=True), "为空时不启用下限。"),
    strategy_param("max_float_market_value", "最大流通市值", "stock_pool", "stock_pool", "基础股票池", money_control(allow_blank=True), "为空时不启用上限。"),
    strategy_param("include_bj", "包含北交所", "stock_pool", "stock_pool", "基础股票池", boolean_control(), "是否允许北交所股票进入股票池。", usage=["filter", "switch"]),
    strategy_param("exclude_star_board", "排除科创板", "stock_pool", "stock_pool", "基础股票池", boolean_control(), "是否排除科创板股票。", usage=["filter", "switch"]),
    strategy_param("missing_turnover_policy", "换手率缺失", "stock_pool", "missing_data", "缺失数据处理", select_control([("allow", "保留缺失股票"), ("skip", "跳过缺失股票")]), "控制换手率字段缺失时如何处理。"),
    strategy_param("missing_float_market_value_policy", "流通市值缺失", "stock_pool", "missing_data", "缺失数据处理", select_control([("allow", "保留缺失股票"), ("skip", "跳过缺失股票")]), "控制流通市值缺失时如何处理。"),
    strategy_param("breakout_pullback_direction", "形态方向", "technical", "breakout_pullback", "突破回踩", select_control([("both", "突破与回踩都看"), ("breakout", "只看右侧突破"), ("pullback", "只看左侧回踩")]), "控制突破回踩模式关注的形态方向。"),
    strategy_param("breakout_lookback", "突破观察天数", "technical", "breakout_pullback", "突破回踩", number_control(unit="日", min_value=5), "观察阶段高点和回踩位置的窗口。"),
    strategy_param("pullback_tolerance", "回踩容忍", "technical", "breakout_pullback", "突破回踩", number_control(unit="比例", min_value=0), "价格贴近短期均线的容忍距离。"),
    strategy_param("platform_lookback_days", "平台观察天数", "platform", "platform_range", "平台区间", number_control(unit="日", min_value=10), "平台窗口长度。"),
    strategy_param("platform_range_basis", "平台振幅口径", "platform", "platform_range", "平台区间", select_control([("high_low", "最高价 / 最低价"), ("close", "收盘价区间")]), "决定平台振幅按影线还是收盘价计算。"),
    strategy_param("platform_max_range_mode", "平台区间条件", "platform", "platform_range", "平台区间", select_control(CONDITION_OPTIONS), "控制平台振幅是必须条件、得分项还是关闭。"),
    strategy_param("platform_max_range", "平台区间最大振幅", "platform", "platform_range", "平台区间", number_control(unit="比例", min_value=0), "平台最高到最低的最大允许振幅。"),
    strategy_param("platform_min_bullish_ratio", "最小阳线占比", "platform", "platform_range", "平台区间", number_control(unit="比例", min_value=0, max_value=1), "平台内红柱占比下限。"),
    strategy_param("platform_bullish_ratio_mode", "阳线占比条件", "platform", "platform_range", "平台区间", select_control(CONDITION_OPTIONS), "控制阳线占比的使用方式。"),
    strategy_param("platform_bullish_ratio_score", "阳线占比加分线", "platform", "platform_range", "平台区间", number_control(unit="比例", min_value=0, max_value=1), "达到该比例时增加形态质量分。", usage=["score"]),
    strategy_param("platform_bull_volume_advantage", "阳线均量优势", "platform", "platform_range", "平台区间", number_control(unit="倍", min_value=0), "平台红柱均量 / 绿柱均量下限。"),
    strategy_param("platform_bull_volume_advantage_mode", "阳线均量条件", "platform", "platform_range", "平台区间", select_control(CONDITION_OPTIONS), "控制阳线均量优势的使用方式。"),
    strategy_param("platform_bull_volume_advantage_score", "阳线量能加分线", "platform", "platform_range", "平台区间", number_control(unit="倍", min_value=0), "达到该倍数时增加量能质量分。", usage=["score"]),
    strategy_param("platform_breakout_clearance_mode", "突破幅度条件", "platform", "platform_breakout", "突破确认", select_control(CONDITION_OPTIONS), "控制突破上沿最小幅度的使用方式。"),
    strategy_param("platform_breakout_require_close_above", "收盘站上平台", "platform", "platform_breakout", "突破确认", boolean_control(), "是否要求收盘价站在平台上沿之上。", usage=["filter", "switch"]),
    strategy_param("platform_breakout_clearance", "突破上沿最小幅度", "platform", "platform_breakout", "突破确认", number_control(unit="比例", min_value=0), "最新收盘价高于平台上沿的最小幅度。"),
    strategy_param("platform_breakout_max_clearance", "突破上沿最大距离", "platform", "platform_breakout", "突破确认", number_control(unit="比例", min_value=0), "距离平台过远时视为追高。"),
    strategy_param("platform_breakout_max_clearance_mode", "最大距离条件", "platform", "platform_breakout", "突破确认", select_control(CONDITION_OPTIONS), "控制突破上沿最大距离的使用方式。"),
    strategy_param("platform_breakout_first_mode", "首次突破条件", "platform", "platform_breakout", "突破确认", select_control(CONDITION_OPTIONS), "控制是否要求首次有效突破。"),
    strategy_param("platform_breakout_volume_ratio", "突破量比", "platform", "platform_breakout", "突破确认", number_control(unit="倍", min_value=0), "最新成交量 / 平台均量下限。"),
    strategy_param("platform_breakout_volume_ratio_mode", "突破量比条件", "platform", "platform_breakout", "突破确认", select_control(CONDITION_OPTIONS), "控制突破量比的使用方式。"),
    strategy_param("platform_breakout_pct_chg_min", "突破涨幅下限", "platform", "platform_breakout", "突破确认", number_control(unit="%", min_value=-20, max_value=20), "突破当天涨跌幅下限。"),
    strategy_param("platform_breakout_pct_chg_mode", "突破涨幅条件", "platform", "platform_breakout", "突破确认", select_control(CONDITION_OPTIONS), "控制突破涨幅的使用方式。"),
    strategy_param("platform_breakout_bullish_mode", "突破红柱条件", "platform", "platform_breakout", "突破确认", select_control(CONDITION_OPTIONS), "控制突破 K 线是否必须收红。"),
    strategy_param("platform_body_strength_min", "突破实体强度", "platform", "platform_breakout", "突破确认", number_control(min_value=0), "红柱实体 / 上下影线总和。"),
    strategy_param("platform_body_strength_mode", "实体强度条件", "platform", "platform_breakout", "突破确认", select_control(CONDITION_OPTIONS), "控制实体强度的使用方式。"),
    strategy_param("macd_position", "MACD 位置", "platform", "platform_breakout", "突破确认", select_control([("dif_above_zero", "DIF 在 0 轴上方"), ("dif_dea_above_zero", "DIF 与 DEA 均在 0 轴上方")]), "平台突破使用的 MACD 位置条件。"),
    strategy_param("platform_ma_trend_enabled", "启用均线趋势", "platform", "platform_ma", "平台均线", boolean_control(), "是否检查平台突破时的均线状态。", usage=["switch"]),
    strategy_param("platform_ma_bullish_mode", "均线多头条件", "platform", "platform_ma", "平台均线", select_control(CONDITION_OPTIONS), "控制均线多头排列的使用方式。"),
    strategy_param("platform_ma_rising_required", "要求均线上升", "platform", "platform_ma", "平台均线", boolean_control(), "是否要求关键均线向上。", usage=["switch"]),
    strategy_param("platform_ma_rising_mode", "均线上升条件", "platform", "platform_ma", "平台均线", select_control(CONDITION_OPTIONS), "控制均线上升的使用方式。"),
    strategy_param("platform_macd_filter_mode", "平台 MACD 条件", "platform", "platform_ma", "平台均线", select_control(CONDITION_OPTIONS), "控制 MACD 过滤的使用方式。"),
    strategy_param("platform_setup_lookback_days", "平台观察天数", "platform", "platform_setup", "平台临界观察", number_control(unit="日", min_value=10), "平台临界窗口长度。"),
    strategy_param("platform_setup_max_range", "平台最大振幅", "platform", "platform_setup", "平台临界观察", number_control(unit="比例", min_value=0), "平台临界模式下的最大区间振幅。"),
    strategy_param("platform_setup_max_distance_to_high", "接近上沿距离", "platform", "platform_setup", "平台临界观察", number_control(unit="比例", min_value=0), "最新价距离平台上沿的最大距离。"),
    strategy_param("platform_setup_max_recent_gain_5d", "近5日涨幅上限", "platform", "platform_setup", "平台临界观察", number_control(unit="比例", min_value=0), "防止平台临界提前走远。"),
    strategy_param("platform_setup_volume_contraction_max", "缩量整理上限", "platform", "platform_setup", "平台临界观察", number_control(unit="倍", min_value=0), "平台内成交量不能明显放大。"),
    strategy_param("platform_setup_bull_volume_advantage", "阳线均量优势", "platform", "platform_setup", "平台临界观察", number_control(unit="倍", min_value=0), "阳线均量相对阴线均量的优势。"),
    strategy_param("platform_setup_ma_convergence_max", "均线粘合上限", "platform", "platform_setup", "平台临界观察", number_control(unit="比例", min_value=0), "短中期均线距离的最大允许值。"),
    strategy_param("platform_setup_require_ma_turning", "要求 MA5 拐头", "platform", "platform_setup", "平台临界观察", boolean_control(), "是否要求短均线开始向上。", usage=["switch"]),
    strategy_param("platform_setup_macd_mode", "MACD 状态", "platform", "platform_setup", "平台临界观察", select_control([("none", "不启用"), ("dif_above_dea", "DIF 强于 DEA"), ("dif_above_zero", "DIF 在 0 轴上方")]), "平台临界使用的 MACD 状态。"),
    strategy_param("trend_ema_fast_window", "EMA 快线", "trend", "trend_ema", "趋势均线", number_control(unit="日", min_value=2), "短线趋势 EMA 周期。"),
    strategy_param("trend_ema_mid_window", "EMA 中线", "trend", "trend_ema", "趋势均线", number_control(unit="日", min_value=3), "节奏线 EMA 周期。"),
    strategy_param("trend_ema_long_window", "EMA 长线", "trend", "trend_ema", "趋势均线", number_control(unit="日", min_value=5), "中期趋势 EMA 周期。"),
    strategy_param("trend_entry_signal", "趋势信号", "trend", "trend_ema", "趋势均线", select_control([("any", "全部趋势信号"), ("thunder", "强动能确认"), ("follow", "趋势延续"), ("stealth", "早期转强")]), "控制趋势共振关注的入场信号。"),
    strategy_param("trend_require_price_above_ema_long", "要求站上 EMA60", "trend", "trend_ema", "趋势均线", boolean_control(), "是否要求价格站上长期 EMA。", usage=["switch"]),
    strategy_param("trend_require_ema_long_rising", "要求 EMA60 上升", "trend", "trend_ema", "趋势均线", boolean_control(), "是否要求长期 EMA 上升。", usage=["switch"]),
    strategy_param("trend_require_ema_fast_above_mid", "要求 EMA13 高于 EMA21", "trend", "trend_ema", "趋势均线", boolean_control(), "是否要求快线高于中线。", usage=["switch"]),
    strategy_param("trend_macd_fast", "MACD 快线", "trend", "trend_macd", "趋势动能", number_control(min_value=2), "趋势共振 MACD 快线参数。"),
    strategy_param("trend_macd_slow", "MACD 慢线", "trend", "trend_macd", "趋势动能", number_control(min_value=3), "趋势共振 MACD 慢线参数。"),
    strategy_param("trend_macd_signal", "MACD 信号线", "trend", "trend_macd", "趋势动能", number_control(min_value=2), "趋势共振 MACD 信号线参数。"),
    strategy_param("trend_macd_mode", "MACD 条件", "trend", "trend_macd", "趋势动能", select_control([("dif_above_dea", "DIF 强于 DEA"), ("dif_above_zero", "DIF 在 0 轴上方"), ("dif_dea_above_zero", "DIF 与 DEA 均在 0 轴上方"), ("off", "不启用")]), "趋势共振中的 MACD 条件。"),
    strategy_param("trend_stoch_window", "随机周期", "trend", "trend_stoch", "随机指标", number_control(min_value=5), "慢速随机指标窗口。"),
    strategy_param("trend_stoch_k_smooth", "随机 K 平滑", "trend", "trend_stoch", "随机指标", number_control(min_value=1), "K 线平滑参数。"),
    strategy_param("trend_stoch_d_smooth", "随机 D 平滑", "trend", "trend_stoch", "随机指标", number_control(min_value=1), "D 线平滑参数。"),
    strategy_param("trend_stoch_mode", "随机条件", "trend", "trend_stoch", "随机指标", select_control([("k_above_d", "K 在 D 上方"), ("cross_up", "要求 K 上穿 D"), ("off", "不启用")]), "趋势共振中的随机确认方式。"),
    strategy_param("trend_max_ema_mid_distance", "距 EMA21 上限", "trend", "trend_risk", "趋势风险", number_control(unit="比例", min_value=0), "防止趋势买点距离节奏线太远。"),
    strategy_param("trend_max_recent_gain_10d", "近10日涨幅上限", "trend", "trend_risk", "趋势风险", number_control(unit="比例", min_value=0), "防止趋势信号过热。"),
    strategy_param("trend_stoch_overheat", "随机过热线", "trend", "trend_risk", "趋势风险", number_control(min_value=0, max_value=100), "随机指标过热扣分线。"),
    strategy_param("ma_short_window", "MA 短期", "technical", "strength_trend", "强弱与趋势", number_control(unit="日", min_value=3), "短期均线周期。"),
    strategy_param("ma_long_window", "MA 长期", "technical", "strength_trend", "强弱与趋势", number_control(unit="日", min_value=4), "长期均线周期。"),
    strategy_param("trend_filter", "趋势过滤", "technical", "strength_trend", "强弱与趋势", select_control([("ma_short_above_long", "短均线在长均线上方"), ("none", "不启用")]), "通用趋势过滤方式。"),
    strategy_param("rps_window", "排序 RPS 周期", "technical", "strength_trend", "强弱与趋势", select_control([("20", "RPS20"), ("60", "RPS60"), ("120", "RPS120")]), "用于排序和旧策略兼容；RPS20/RPS60/RPS120 下限分别独立配置。"),
    strategy_param("min_rps20", "RPS20 下限", "technical", "strength_trend", "强弱与趋势", number_control(allow_blank=True, min_value=0, max_value=100), "RPS20 低于该值时过滤。"),
    strategy_param("min_rps60", "RPS60 下限", "technical", "strength_trend", "强弱与趋势", number_control(allow_blank=True, min_value=0, max_value=100), "RPS60 低于该值时过滤。"),
    strategy_param("min_rps120", "RPS120 下限", "technical", "strength_trend", "强弱与趋势", number_control(allow_blank=True, min_value=0, max_value=100), "RPS120 低于该值时过滤。"),
    strategy_param("max_amplitude", "振幅上限", "technical", "price_volume", "量价触发", number_control(allow_blank=True, unit="比例", min_value=0), "单日振幅超过该值时过滤。"),
    strategy_param("min_turnover", "最小换手率", "quote", "price_volume", "量价触发", number_control(allow_blank=True, unit="%", min_value=0), "低于该换手率时过滤。"),
    strategy_param("max_turnover", "最大换手率", "quote", "price_volume", "量价触发", number_control(allow_blank=True, unit="%", min_value=0), "高于该换手率时过滤或扣分。"),
    strategy_param("min_pct_chg", "最小涨跌幅", "quote", "price_volume", "量价触发", number_control(allow_blank=True, unit="%"), "低于该涨跌幅时过滤。"),
    strategy_param("max_pct_chg", "最大涨跌幅", "quote", "price_volume", "量价触发", number_control(allow_blank=True, unit="%"), "高于该涨跌幅时过滤。"),
    strategy_param("volume_ratio_min", "成交量放大", "quote", "price_volume", "量价触发", number_control(allow_blank=True, unit="倍", min_value=0), "量比低于该值时过滤。"),
    strategy_param("max_ma_distance", "最大均线偏离", "technical", "price_volume", "量价触发", number_control(allow_blank=True, unit="比例", min_value=0), "距离短均线过远时过滤或扣分。"),
    strategy_param("min_topic_count", "最少题材数", "theme", "theme_strength", "题材强度", number_control(allow_blank=True, min_value=0), "低于该题材覆盖数量时过滤。"),
    strategy_param("min_topic_heat", "题材热度下限", "theme", "theme_strength", "题材强度", number_control(allow_blank=True, min_value=0, max_value=100), "低于该题材热度时过滤或降低排序优先级。", usage=["filter", "score"]),
    strategy_param("min_theme_limit_count", "题材涨停数下限", "theme", "theme_strength", "题材强度", number_control(allow_blank=True, min_value=0), "所属题材内涨停家数不足时过滤。", usage=["filter", "score"]),
    strategy_param("candidate_limit", "候选上限", "stock_pool", "output", "输出设置", number_control(min_value=1, max_value=500), "每次分析最多输出的候选数量。"),
    strategy_param("sort_by", "排序", "stock_pool", "output", "输出设置", select_control([("signal_score", "信号分数"), ("rps20", "RPS20"), ("amount", "成交额"), ("pct_chg", "涨跌幅")]), "候选排序字段。", usage=["sort"]),
]


INDICATORS: List[Dict[str, Any]] = DATA_INDICATORS + STRATEGY_PARAM_INDICATORS


BASE_STOCK_POOL_FIELDS = [
    "min_price",
    "min_amount",
    "min_float_market_value",
    "max_float_market_value",
    "include_bj",
    "exclude_star_board",
    "missing_turnover_policy",
    "missing_float_market_value_policy",
]


def mode_field(indicator_id: str, role: str = "filter") -> Dict[str, str]:
    indicator = INDICATOR_BY_ID[indicator_id]
    return {
        "indicator_id": indicator_id,
        "role": role,
        "group_id": indicator["group_id"],
        "group_label": indicator["group_label"],
    }


INDICATOR_BY_ID = {indicator["id"]: indicator for indicator in INDICATORS}


def mode_fields(indicator_ids: Iterable[str]) -> List[Dict[str, str]]:
    return [mode_field(indicator_id) for indicator_id in indicator_ids]


COMMON_STRENGTH_FIELDS = [
    "ma_short_window",
    "ma_long_window",
    "rps_window",
    "min_rps20",
    "min_rps60",
    "min_rps120",
    "max_amplitude",
    "min_turnover",
    "max_turnover",
    "min_pct_chg",
    "max_pct_chg",
    "volume_ratio_min",
    "max_ma_distance",
    "candidate_limit",
    "sort_by",
]


DEFAULT_SIGNAL_MODES: List[Dict[str, Any]] = [
    {
        "id": "breakout_or_pullback",
        "name": "突破回踩",
        "description": "突破与回踩共用的基础信号模式。",
        "note": "可以保留双形态，也可以只看突破或只看回踩。",
        "runtime_signal_mode": "breakout_or_pullback",
        "fields": mode_fields(BASE_STOCK_POOL_FIELDS + ["breakout_pullback_direction", "pullback_tolerance"] + COMMON_STRENGTH_FIELDS),
        "rule_groups": [],
    },
    {
        "id": "platform_breakout",
        "name": "平台突破",
        "description": "平台收敛后有效突破，并用量能和形态质量确认。",
        "note": "适合右侧确认。",
        "runtime_signal_mode": "platform_breakout",
        "fields": mode_fields(
            BASE_STOCK_POOL_FIELDS
            + [
                "platform_lookback_days",
                "platform_range_basis",
                "platform_max_range_mode",
                "platform_max_range",
                "platform_min_bullish_ratio",
                "platform_bullish_ratio_mode",
                "platform_bullish_ratio_score",
                "platform_bull_volume_advantage",
                "platform_bull_volume_advantage_mode",
                "platform_bull_volume_advantage_score",
                "platform_breakout_clearance_mode",
                "platform_breakout_require_close_above",
                "platform_breakout_clearance",
                "platform_breakout_max_clearance",
                "platform_breakout_max_clearance_mode",
                "platform_breakout_first_mode",
                "platform_breakout_volume_ratio",
                "platform_breakout_volume_ratio_mode",
                "platform_breakout_pct_chg_min",
                "platform_breakout_pct_chg_mode",
                "platform_breakout_bullish_mode",
                "platform_body_strength_min",
                "platform_body_strength_mode",
                "macd_position",
                "platform_ma_bullish_mode",
                "platform_ma_rising_mode",
                "platform_macd_filter_mode",
            ]
            + COMMON_STRENGTH_FIELDS
        ),
        "rule_groups": [
            {
                "id": "score",
                "label": "组合条件",
                "rules": [
                    {
                        "id": "volume_confirms_breakout",
                        "name": "放量确认突破",
                        "kind": "interaction",
                        "indicator_ids": ["platform_breakout_clearance", "volume_ratio"],
                        "expression": "突破上沿距离达标，并且量比达到设定阈值",
                        "effect": {"type": "score", "value": 18},
                        "missing_policy": "neutral",
                        "editable": True,
                    }
                ],
            }
        ],
    },
    {
        "id": "platform_setup",
        "name": "平台临界",
        "description": "还没突破但贴近平台上沿，适合提前放入观察。",
        "note": "适合观察池和盘中雷达。",
        "runtime_signal_mode": "platform_setup",
        "fields": mode_fields(
            BASE_STOCK_POOL_FIELDS
            + [
                "platform_setup_lookback_days",
                "platform_setup_max_range",
                "platform_setup_max_distance_to_high",
                "platform_setup_max_recent_gain_5d",
                "platform_setup_volume_contraction_max",
                "platform_setup_bull_volume_advantage",
                "platform_setup_ma_convergence_max",
                "platform_setup_require_ma_turning",
                "platform_setup_macd_mode",
            ]
            + [field for field in COMMON_STRENGTH_FIELDS if field != "volume_ratio_min"]
        ),
        "rule_groups": [],
    },
    {
        "id": "trend_resonance",
        "name": "趋势共振",
        "description": "EMA、MACD 和随机指标共同确认趋势强度。",
        "note": "适合中短线趋势观察。",
        "runtime_signal_mode": "trend_resonance",
        "fields": mode_fields(
            BASE_STOCK_POOL_FIELDS
            + [
                "trend_ema_fast_window",
                "trend_ema_mid_window",
                "trend_ema_long_window",
                "trend_entry_signal",
                "trend_require_price_above_ema_long",
                "trend_require_ema_long_rising",
                "trend_require_ema_fast_above_mid",
                "trend_macd_fast",
                "trend_macd_slow",
                "trend_macd_signal",
                "trend_macd_mode",
                "trend_stoch_window",
                "trend_stoch_k_smooth",
                "trend_stoch_d_smooth",
                "trend_stoch_mode",
                "trend_max_ema_mid_distance",
                "trend_max_recent_gain_10d",
                "trend_stoch_overheat",
            ]
            + COMMON_STRENGTH_FIELDS
        ),
        "rule_groups": [
            {
                "id": "score",
                "label": "组合条件",
                "rules": [
                    {
                        "id": "trend_low_resistance",
                        "name": "趋势与筹码低阻力",
                        "kind": "interaction",
                        "indicator_ids": ["rps20", "cyq_winner_rate", "cost_50pct"],
                        "expression": "RPS 强，筹码胜率改善，当前价没有明显脱离中位成本",
                        "effect": {"type": "score", "value": 16},
                        "missing_policy": "neutral",
                        "editable": True,
                    }
                ],
            }
        ],
    },
    {
        "id": "theme_resonance_breakout",
        "name": "题材共振突破",
        "description": "平台突破叠加题材热度与量能确认。",
        "note": "偏 A 股主线题材的突破确认。",
        "runtime_signal_mode": "platform_breakout",
        "fields": mode_fields(
            BASE_STOCK_POOL_FIELDS
            + [
                "platform_breakout_clearance",
                "platform_breakout_volume_ratio",
                "min_topic_count",
                "min_topic_heat",
                "min_theme_limit_count",
                "max_turnover",
                "candidate_limit",
                "sort_by",
            ]
        )
        + [
            mode_field("topic_count", "display"),
            mode_field("topic_heat", "score"),
            mode_field("theme_limit_count", "score"),
        ],
        "rule_groups": [
            {
                "id": "interaction",
                "label": "组合条件",
                "rules": [
                    {
                        "id": "theme_volume_breakout",
                        "name": "题材放量共振",
                        "kind": "interaction",
                        "indicator_ids": ["platform_breakout_clearance", "volume_ratio", "topic_heat"],
                        "expression": "突破上沿达标，并且量比放大，并且题材热度达到阈值",
                        "effect": {"type": "score", "value": 22},
                        "missing_policy": "neutral",
                        "editable": True,
                    }
                ],
            }
        ],
    },
]


DEFAULT_MODE_FIELD_EXTENSIONS = {
    "theme_resonance_breakout": [
        ("min_topic_count", "filter"),
        ("min_topic_heat", "score"),
        ("min_theme_limit_count", "score"),
        ("topic_count", "display"),
    ],
}


def blank_signal_mode(name: str = "新信号模式") -> Dict[str, Any]:
    return {
        "id": "",
        "name": name.strip() or "新信号模式",
        "description": "从基础股票池开始，自行添加需要的指标和组合条件。",
        "note": "",
        "runtime_signal_mode": "breakout_or_pullback",
        "fields": mode_fields(BASE_STOCK_POOL_FIELDS),
        "rule_groups": [],
    }


def normalize_signal_mode(mode: Dict[str, Any]) -> Dict[str, Any]:
    indicator_ids = {indicator["id"] for indicator in INDICATORS}
    normalized = deepcopy(mode)
    normalized["name"] = str(normalized.get("name") or "新信号模式").strip() or "新信号模式"
    normalized["description"] = str(normalized.get("description") or "")
    normalized["note"] = str(normalized.get("note") or "")
    normalized["runtime_signal_mode"] = normalized.get("runtime_signal_mode") or "breakout_or_pullback"
    fields = []
    seen = set()
    for field in normalized.get("fields") or []:
        indicator_id = field.get("indicator_id")
        if indicator_id not in indicator_ids or indicator_id in seen:
            continue
        seen.add(indicator_id)
        indicator = INDICATOR_BY_ID[indicator_id]
        fields.append(
            {
                "indicator_id": indicator_id,
                "role": field.get("role") or indicator.get("default_role") or "filter",
                "group_id": field.get("group_id") or indicator["group_id"],
                "group_label": field.get("group_label") or indicator["group_label"],
            }
        )
    for indicator_id, role in DEFAULT_MODE_FIELD_EXTENSIONS.get(str(normalized.get("id") or ""), []):
        if indicator_id in indicator_ids and indicator_id not in seen:
            seen.add(indicator_id)
            fields.append(mode_field(indicator_id, role))
    normalized["fields"] = fields or mode_fields(BASE_STOCK_POOL_FIELDS)
    rule_groups = []
    for group in normalized.get("rule_groups") or []:
        rules = []
        for rule in group.get("rules") or []:
            rule_indicator_ids = [indicator_id for indicator_id in rule.get("indicator_ids", []) if indicator_id in indicator_ids]
            if not rule_indicator_ids:
                continue
            rules.append(
                {
                    "id": str(rule.get("id") or f"rule-{len(rules) + 1}"),
                    "name": str(rule.get("name") or "组合条件"),
                    "kind": rule.get("kind") if rule.get("kind") in {"filter", "score", "risk", "interaction"} else "interaction",
                    "indicator_ids": rule_indicator_ids,
                    "expression": str(rule.get("expression") or ""),
                    "effect": rule.get("effect") or {"type": "score", "value": 0},
                    "missing_policy": rule.get("missing_policy") or "neutral",
                    "editable": bool(rule.get("editable", True)),
                }
            )
        if rules:
            rule_groups.append({"id": str(group.get("id") or f"group-{len(rule_groups) + 1}"), "label": str(group.get("label") or "组合条件"), "rules": rules})
    normalized["rule_groups"] = rule_groups
    normalized.pop("base_signal_mode", None)
    return normalized


def indicator_library(signal_modes: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    indicators = deepcopy(INDICATORS)
    categories = deepcopy(INDICATOR_CATEGORIES)
    return {
        "categories": categories,
        "indicators": indicators,
        "signal_modes": [],
        "summary": {
            "category_count": len(categories),
            "indicator_count": len(indicators),
            "active_count": sum(1 for item in indicators if item["status"] == "active"),
            "available_count": sum(1 for item in indicators if item["status"] == "available"),
            "planned_count": sum(1 for item in indicators if item["status"] == "planned"),
            "strategy_param_count": sum(1 for item in indicators if item.get("kind") == "strategy_param"),
            "signal_mode_count": 0,
            "interaction_rule_count": 0,
        },
    }
