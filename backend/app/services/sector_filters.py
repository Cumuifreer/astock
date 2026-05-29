from __future__ import annotations

from typing import Any, List, Tuple


NON_THEME_CONCEPT_PREFIXES = (
    "同花顺",
)

NON_THEME_CONCEPT_KEYWORDS = (
    "沪深京",
    "沪深等权",
    "上证指数",
    "深证",
    "指数",
    "沪股通",
    "深股通",
    "陆股通",
    "QFII",
    "融资融券",
    "昨日",
    "近期",
    "百日",
    "打板",
    "首板",
    "涨停表现",
    "主板",
    "中盘",
    "小盘",
    "大盘",
    "高盈利",
    "低盈利",
    "高股息",
    "高估值",
    "低估值",
    "高贝塔",
    "高动量",
    "低动量",
    "均衡动量",
    "均衡盈利",
    "激进投资",
    "保守投资",
    "创历史",
    "最近多板",
    "社保新进",
    "业绩预",
    "减持",
    "重仓",
)


NON_THEME_CONCEPT_PATTERNS = (
    "%(A股)%",
    "%（A股）%",
)


def concept_theme_filter_sql(column: str) -> Tuple[str, List[Any]]:
    parts = [f"{column} IS NOT NULL", f"TRIM({column}) <> ''"]
    params: List[Any] = []
    for prefix in NON_THEME_CONCEPT_PREFIXES:
        parts.append(f"{column} NOT ILIKE ?")
        params.append(f"{prefix}%")
    for keyword in NON_THEME_CONCEPT_KEYWORDS:
        parts.append(f"{column} NOT ILIKE ?")
        params.append(f"%{keyword}%")
    for pattern in NON_THEME_CONCEPT_PATTERNS:
        parts.append(f"{column} NOT LIKE ?")
        params.append(pattern)
    return "(" + " AND ".join(parts) + ")", params
