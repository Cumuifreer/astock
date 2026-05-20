from backend.app.services.market_utils import normalize_a_share_code


def test_normalizes_common_a_share_formats():
    assert normalize_a_share_code("sh.600000") == "600000.SH"
    assert normalize_a_share_code("sz000001") == "000001.SZ"
    assert normalize_a_share_code("300750") == "300750.SZ"
    assert normalize_a_share_code("688001") == "688001.SH"


def test_excludes_non_stock_and_optional_markets_by_default():
    assert normalize_a_share_code("sh.000001") is None
    assert normalize_a_share_code("900901") is None
    assert normalize_a_share_code("200002") is None
    assert normalize_a_share_code("510300") is None
    assert normalize_a_share_code("430047") is None
    assert normalize_a_share_code("688001", exclude_star=True) is None


def test_can_include_beijing_exchange_when_configured():
    assert normalize_a_share_code("430047", include_bj=True) == "430047.BJ"
