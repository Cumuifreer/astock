import sys
from pathlib import Path

import pandas as pd
import pytest

from backend.app.config import _load_env_file, settings
from backend.app.sources.base import SourceUnavailable
from backend.app.sources.tushare_client import create_tushare_pro


def test_load_env_file_sets_values_without_overriding_existing_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "ASHARE_TUSHARE_TOKEN=from-file",
                "ASHARE_TUSHARE_HTTP_URL='http://101.35.233.113:8020/'",
                "ASHARE_TUSHARE_REALTIME=1",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ASHARE_TUSHARE_TOKEN", "from-shell")
    monkeypatch.delenv("ASHARE_TUSHARE_HTTP_URL", raising=False)

    _load_env_file(Path(env_file))

    assert sys.modules
    assert __import__("os").environ["ASHARE_TUSHARE_TOKEN"] == "from-shell"
    assert __import__("os").environ["ASHARE_TUSHARE_HTTP_URL"] == "http://101.35.233.113:8020/"


def test_create_tushare_pro_sets_required_relay_http_url(monkeypatch):
    class FakePro:
        def index_basic(self, limit=0):
            return pd.DataFrame([{"limit": limit}])

    class FakeTushare:
        def __init__(self):
            self.token = None

        def pro_api(self, token):
            self.token = token
            return FakePro()

        def pro_bar(self, api, ts_code="", limit=0):
            assert getattr(api, "_DataApi__http_url") == settings.tushare_http_url
            return pd.DataFrame([{"ts_code": ts_code, "limit": limit}])

    fake = FakeTushare()
    monkeypatch.setitem(sys.modules, "tushare", fake)

    ts, pro = create_tushare_pro("test-token")

    assert ts is fake
    assert fake.token == "test-token"
    assert getattr(pro, "_DataApi__http_url") == "http://101.35.233.113:8020/"
    assert pro.index_basic(limit=5).iloc[0]["limit"] == 5
    assert ts.pro_bar(api=pro, ts_code="000001.SZ", limit=3).iloc[0]["ts_code"] == "000001.SZ"


def test_create_tushare_pro_missing_token_mentions_env_and_relay():
    with pytest.raises(SourceUnavailable) as exc:
        create_tushare_pro(token="")

    message = str(exc.value)
    assert "ASHARE_TUSHARE_TOKEN" in message
    assert "_TUSHARE_HTTP_URL" in message or "101.35.233.113:8020" in message
