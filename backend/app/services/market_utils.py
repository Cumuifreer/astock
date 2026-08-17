from __future__ import annotations

import math
import re
from typing import Any, Optional


SH_PREFIXES = ("600", "601", "603", "605", "688")
SZ_PREFIXES = ("000", "001", "002", "003", "300", "301")
BJ_PREFIXES = (
    "430",
    "830",
    "831",
    "832",
    "833",
    "834",
    "835",
    "836",
    "837",
    "838",
    "839",
    "870",
    "871",
    "872",
    "873",
    "874",
    "875",
    "876",
    "877",
    "878",
    "879",
    "920",
)


def normalize_a_share_code(
    raw: Any,
    include_bj: bool = False,
    exclude_star: bool = False,
) -> Optional[str]:
    if raw is None:
        return None
    value = str(raw).strip().upper()
    if not value:
        return None

    exchange = None
    suffix_match = re.match(r"^(\d{6})[.\-_]?(SH|SZ|BJ)$", value)
    prefix_match = re.match(r"^(SH|SZ|BJ)[.\-_]?(\d{6})$", value)
    if suffix_match:
        code, exchange = suffix_match.group(1), suffix_match.group(2)
    elif prefix_match:
        exchange, code = prefix_match.group(1), prefix_match.group(2)
    else:
        digits = re.sub(r"\D", "", value)
        if len(digits) != 6:
            return None
        code = digits

    if not code.isdigit() or len(code) != 6:
        return None

    if code.startswith(("900", "200")):
        return None
    if code.startswith(("10", "11", "12", "13", "15", "16", "18", "50", "51", "52", "56", "58")):
        return None

    if exchange == "SH":
        if not code.startswith(SH_PREFIXES):
            return None
        inferred = "SH"
    elif exchange == "SZ":
        if not code.startswith(SZ_PREFIXES):
            return None
        inferred = "SZ"
    elif exchange == "BJ":
        if not code.startswith(BJ_PREFIXES):
            return None
        inferred = "BJ"
    elif code.startswith(SH_PREFIXES):
        inferred = "SH"
    elif code.startswith(SZ_PREFIXES):
        inferred = "SZ"
    elif code.startswith(BJ_PREFIXES):
        inferred = "BJ"
    else:
        return None

    if inferred == "BJ" and not include_bj:
        return None
    if inferred == "SH" and code.startswith("688") and exclude_star:
        return None
    return f"{code}.{inferred}"


def to_baostock_code(code: str) -> str:
    symbol, exchange = code.split(".")
    return f"{exchange.lower()}.{symbol}"


def to_plain_code(code: str) -> str:
    return code.split(".")[0]


def to_sina_chart_symbol(code: str) -> str:
    symbol, exchange = code.split(".")
    return f"{exchange.lower()}{symbol}"


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if value == "":
            return None
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except (TypeError, ValueError):
        return None


def safe_bool_from_flag(value: Any) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "是"}
