from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_env_file(path: Path | None = None) -> None:
    env_path = path or Path(os.getenv("ASHARE_ENV_FILE", PROJECT_ROOT / ".env"))
    if not env_path.exists():
        return
    entries: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            entries[key] = value

    def entry_enabled(name: str) -> bool:
        value = os.environ.get(name, entries.get(name, "0"))
        return value.strip().lower() in {"1", "true", "yes", "on"}

    blocked_secrets = set()
    if not entry_enabled("ASHARE_LLM_ENABLED"):
        blocked_secrets.update({"ASHARE_DAILY_BRIEF_API_KEY", "DEEPSEEK_API_KEY", "LLM_API_KEY"})
    if not entry_enabled("ASHARE_TUSHARE_ENABLED"):
        blocked_secrets.update({"ASHARE_TUSHARE_TOKEN", "TUSHARE_TOKEN"})
    for key, value in entries.items():
        if key not in blocked_secrets:
            os.environ.setdefault(key, value)


_load_env_file()


def _env_enabled(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _enabled_secret(enabled: bool, *names: str) -> str:
    if not enabled:
        return ""
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


LLM_ENABLED = _env_enabled("ASHARE_LLM_ENABLED")
TUSHARE_ENABLED = _env_enabled("ASHARE_TUSHARE_ENABLED")


@dataclass(frozen=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    data_dir: Path = Path(os.getenv("ASHARE_DATA_DIR", PROJECT_ROOT / "data"))
    db_path: Path = Path(
        os.getenv("ASHARE_DB_PATH", PROJECT_ROOT / "data" / "ashare_signal.duckdb")
    )
    frontend_dist: Path = Path(
        os.getenv("ASHARE_FRONTEND_DIST", PROJECT_ROOT / "frontend" / "dist")
    )
    source_probe_ttl_minutes: int = int(os.getenv("ASHARE_SOURCE_PROBE_TTL_MINUTES", "60"))
    default_history_days: int = int(os.getenv("ASHARE_HISTORY_DAYS", "180"))
    update_limit: int = int(os.getenv("ASHARE_UPDATE_LIMIT", "0"))
    include_bj: bool = os.getenv("ASHARE_INCLUDE_BJ", "0") == "1"
    exclude_star_board: bool = os.getenv("ASHARE_EXCLUDE_STAR_BOARD", "0") == "1"
    baostock_min_delay: float = float(os.getenv("ASHARE_BAOSTOCK_MIN_DELAY", "0.12"))
    baostock_max_delay: float = float(os.getenv("ASHARE_BAOSTOCK_MAX_DELAY", "0.45"))
    baostock_socket_timeout_seconds: float = float(os.getenv("ASHARE_BAOSTOCK_SOCKET_TIMEOUT", "30"))
    baostock_max_consecutive_failures: int = int(
        os.getenv("ASHARE_BAOSTOCK_MAX_CONSECUTIVE_FAILURES", "8")
    )
    baostock_industry_refresh_days: int = int(os.getenv("ASHARE_BAOSTOCK_INDUSTRY_REFRESH_DAYS", "30"))
    public_source_min_delay: float = float(os.getenv("ASHARE_PUBLIC_SOURCE_MIN_DELAY", "0.8"))
    public_source_max_delay: float = float(os.getenv("ASHARE_PUBLIC_SOURCE_MAX_DELAY", "2.2"))
    sina_page_min_delay: float = float(os.getenv("ASHARE_SINA_PAGE_MIN_DELAY", "0.35"))
    sina_page_max_delay: float = float(os.getenv("ASHARE_SINA_PAGE_MAX_DELAY", "0.75"))
    sina_request_timeout_seconds: int = int(os.getenv("ASHARE_SINA_REQUEST_TIMEOUT", "12"))
    sina_total_timeout_seconds: int = int(os.getenv("ASHARE_SINA_TOTAL_TIMEOUT", "120"))
    sina_min_interval_minutes: int = int(os.getenv("ASHARE_SINA_MIN_INTERVAL_MINUTES", "12"))
    sina_failure_cooldown_minutes: int = int(os.getenv("ASHARE_SINA_FAILURE_COOLDOWN_MINUTES", "180"))
    intraday_scheduler_enabled: bool = os.getenv("ASHARE_INTRADAY_SCHEDULER", "1") == "1"
    intraday_scheduler_poll_seconds: int = int(os.getenv("ASHARE_INTRADAY_SCHEDULER_POLL_SECONDS", "30"))
    intraday_scheduler_catchup_minutes: int = int(os.getenv("ASHARE_INTRADAY_SCHEDULER_CATCHUP_MINUTES", "8"))
    intraday_schedule: str = os.getenv("ASHARE_INTRADAY_SCHEDULE", "")
    intraday_retention_days: int = int(os.getenv("ASHARE_INTRADAY_RETENTION_DAYS", "10"))
    tushare_enabled: bool = TUSHARE_ENABLED
    tushare_enrichment_enabled: bool = TUSHARE_ENABLED and _env_enabled("ASHARE_TUSHARE_ENRICHMENT", "1")
    tushare_enrichment_code_limit: int = int(os.getenv("ASHARE_TUSHARE_ENRICHMENT_CODE_LIMIT", "200"))
    tushare_enrichment_timeout_seconds: int = int(os.getenv("ASHARE_TUSHARE_ENRICHMENT_TIMEOUT", "240"))
    tushare_enrichment_loop_delay: float = float(os.getenv("ASHARE_TUSHARE_ENRICHMENT_LOOP_DELAY", "0.13"))
    tushare_history_enabled: bool = TUSHARE_ENABLED and _env_enabled("ASHARE_TUSHARE_HISTORY", "1")
    tushare_history_timeout_seconds: int = int(os.getenv("ASHARE_TUSHARE_HISTORY_TIMEOUT", "900"))
    daily_brief_scheduler_enabled: bool = os.getenv("ASHARE_DAILY_BRIEF_SCHEDULER", "1") == "1"
    daily_brief_scheduler_poll_seconds: int = int(os.getenv("ASHARE_DAILY_BRIEF_POLL_SECONDS", "60"))
    daily_brief_schedule_time: str = os.getenv("ASHARE_DAILY_BRIEF_TIME", "08:20")
    daily_update_scheduler_enabled: bool = os.getenv("ASHARE_DAILY_UPDATE_SCHEDULER", "0") == "1"
    daily_update_scheduler_poll_seconds: int = int(os.getenv("ASHARE_DAILY_UPDATE_POLL_SECONDS", "60"))
    daily_update_schedule_time: str = os.getenv("ASHARE_DAILY_UPDATE_TIME", "17:10")
    daily_update_mode: str = os.getenv("ASHARE_DAILY_UPDATE_MODE", "daily_light")
    daily_brief_source_timeout_seconds: int = int(os.getenv("ASHARE_DAILY_BRIEF_SOURCE_TIMEOUT", "12"))
    intraday_strategy_tracking_auto_enabled: bool = os.getenv("ASHARE_INTRADAY_STRATEGY_TRACKING_AUTO", "0") == "1"
    analysis_batch_size: int = int(os.getenv("ASHARE_ANALYSIS_BATCH_SIZE", "300"))
    llm_enabled: bool = LLM_ENABLED
    daily_brief_api_key: str = _enabled_secret(LLM_ENABLED, "ASHARE_DAILY_BRIEF_API_KEY", "DEEPSEEK_API_KEY")
    daily_brief_model: str = os.getenv("ASHARE_DAILY_BRIEF_MODEL", "deepseek-chat") if LLM_ENABLED else "fallback"
    daily_brief_llm_url: str = (
        os.getenv("ASHARE_DAILY_BRIEF_LLM_URL", "https://api.deepseek.com/chat/completions")
        if LLM_ENABLED
        else ""
    )
    tushare_realtime_enabled: bool = TUSHARE_ENABLED and _env_enabled("ASHARE_TUSHARE_REALTIME", "1")
    tushare_token: str = _enabled_secret(TUSHARE_ENABLED, "ASHARE_TUSHARE_TOKEN", "TUSHARE_TOKEN")
    tushare_http_url: str = (
        os.getenv("ASHARE_TUSHARE_HTTP_URL", "http://101.35.233.113:8020/")
        if TUSHARE_ENABLED
        else ""
    )
    tushare_timeout_seconds: int = int(os.getenv("ASHARE_TUSHARE_TIMEOUT_SECONDS", "60"))
    http_basic_username: str = os.getenv("ASHARE_HTTP_BASIC_USERNAME", "").strip()
    http_basic_password: str = os.getenv("ASHARE_HTTP_BASIC_PASSWORD", "").strip()


settings = Settings()
