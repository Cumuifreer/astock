import json
import os
import subprocess
import sys


def test_disabled_integrations_do_not_load_residual_systemd_secrets():
    env = dict(os.environ)
    env.update(
        {
            "ASHARE_LLM_ENABLED": "0",
            "ASHARE_TUSHARE_ENABLED": "0",
            "DEEPSEEK_API_KEY": "residual-deepseek-secret",
            "ASHARE_DAILY_BRIEF_API_KEY": "residual-brief-secret",
            "TUSHARE_TOKEN": "residual-tushare-secret",
            "ASHARE_TUSHARE_TOKEN": "residual-ashare-token",
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json; from backend.app.config import settings; "
                "print(json.dumps({'llm': settings.daily_brief_api_key, "
                "'tushare': settings.tushare_token, 'llm_enabled': settings.llm_enabled, "
                "'tushare_enabled': settings.tushare_enabled}))"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert json.loads(result.stdout) == {
        "llm": "",
        "tushare": "",
        "llm_enabled": False,
        "tushare_enabled": False,
    }


def test_disabled_integrations_skip_secrets_while_loading_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "ASHARE_LLM_ENABLED=0",
                "ASHARE_TUSHARE_ENABLED=0",
                "DEEPSEEK_API_KEY=file-deepseek-secret",
                "ASHARE_TUSHARE_TOKEN=file-tushare-secret",
            ]
        ),
        encoding="utf-8",
    )
    env = dict(os.environ)
    for name in [
        "ASHARE_LLM_ENABLED",
        "ASHARE_TUSHARE_ENABLED",
        "DEEPSEEK_API_KEY",
        "ASHARE_DAILY_BRIEF_API_KEY",
        "TUSHARE_TOKEN",
        "ASHARE_TUSHARE_TOKEN",
    ]:
        env.pop(name, None)
    env["ASHARE_ENV_FILE"] = str(env_file)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json, os; from backend.app.config import settings; "
                "print(json.dumps({'env_llm': os.environ.get('DEEPSEEK_API_KEY'), "
                "'env_tushare': os.environ.get('ASHARE_TUSHARE_TOKEN'), "
                "'llm': settings.daily_brief_api_key, 'tushare': settings.tushare_token}))"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert json.loads(result.stdout) == {
        "env_llm": None,
        "env_tushare": None,
        "llm": "",
        "tushare": "",
    }
