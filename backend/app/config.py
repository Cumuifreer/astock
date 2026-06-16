from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_env_file(path: Path | None = None) -> None:
    env_path = path or Path(os.getenv("ASHARE_ENV_FILE", PROJECT_ROOT / ".env"))
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_env_file()


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
    public_source_min_delay: float = float(os.getenv("ASHARE_PUBLIC_SOURCE_MIN_DELAY", "0.8"))
    public_source_max_delay: float = float(os.getenv("ASHARE_PUBLIC_SOURCE_MAX_DELAY", "2.2"))
    intraday_scheduler_enabled: bool = os.getenv("ASHARE_INTRADAY_SCHEDULER", "1") == "1"
    intraday_scheduler_poll_seconds: int = int(os.getenv("ASHARE_INTRADAY_SCHEDULER_POLL_SECONDS", "30"))
    intraday_scheduler_catchup_minutes: int = int(os.getenv("ASHARE_INTRADAY_SCHEDULER_CATCHUP_MINUTES", "8"))
    intraday_schedule: str = os.getenv("ASHARE_INTRADAY_SCHEDULE", "")
    intraday_retention_days: int = int(os.getenv("ASHARE_INTRADAY_RETENTION_DAYS", "10"))
    tushare_enrichment_enabled: bool = os.getenv("ASHARE_TUSHARE_ENRICHMENT", "1") == "1"
    tushare_enrichment_code_limit: int = int(os.getenv("ASHARE_TUSHARE_ENRICHMENT_CODE_LIMIT", "200"))
    tushare_enrichment_timeout_seconds: int = int(os.getenv("ASHARE_TUSHARE_ENRICHMENT_TIMEOUT", "240"))
    tushare_enrichment_loop_delay: float = float(os.getenv("ASHARE_TUSHARE_ENRICHMENT_LOOP_DELAY", "0.13"))
    tushare_history_enabled: bool = os.getenv("ASHARE_TUSHARE_HISTORY", "1") == "1"
    tushare_history_timeout_seconds: int = int(os.getenv("ASHARE_TUSHARE_HISTORY_TIMEOUT", "900"))
    daily_brief_scheduler_enabled: bool = os.getenv("ASHARE_DAILY_BRIEF_SCHEDULER", "1") == "1"
    daily_brief_scheduler_poll_seconds: int = int(os.getenv("ASHARE_DAILY_BRIEF_POLL_SECONDS", "60"))
    daily_brief_schedule_time: str = os.getenv("ASHARE_DAILY_BRIEF_TIME", "08:20")
    daily_update_scheduler_enabled: bool = os.getenv("ASHARE_DAILY_UPDATE_SCHEDULER", "0") == "1"
    daily_update_scheduler_poll_seconds: int = int(os.getenv("ASHARE_DAILY_UPDATE_POLL_SECONDS", "60"))
    daily_update_schedule_time: str = os.getenv("ASHARE_DAILY_UPDATE_TIME", "17:10")
    daily_update_mode: str = os.getenv("ASHARE_DAILY_UPDATE_MODE", "daily_light")
    daily_brief_source_timeout_seconds: int = int(os.getenv("ASHARE_DAILY_BRIEF_SOURCE_TIMEOUT", "12"))
    daily_brief_api_key: str = os.getenv("ASHARE_DAILY_BRIEF_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
    daily_brief_model: str = os.getenv("ASHARE_DAILY_BRIEF_MODEL", "deepseek-chat")
    daily_brief_llm_url: str = os.getenv("ASHARE_DAILY_BRIEF_LLM_URL", "https://api.deepseek.com/chat/completions")
    intraday_strategy_tracking_auto_enabled: bool = os.getenv("ASHARE_INTRADAY_STRATEGY_TRACKING_AUTO", "0") == "1"
    tushare_realtime_enabled: bool = os.getenv("ASHARE_TUSHARE_REALTIME", "1") == "1"
    tushare_token: str = os.getenv("ASHARE_TUSHARE_TOKEN") or os.getenv("TUSHARE_TOKEN", "")
    tushare_http_url: str = os.getenv("ASHARE_TUSHARE_HTTP_URL", "http://101.35.233.113:8020/")
    tushare_timeout_seconds: int = int(os.getenv("ASHARE_TUSHARE_TIMEOUT_SECONDS", "60"))
    analysis_batch_size: int = int(os.getenv("ASHARE_ANALYSIS_BATCH_SIZE", "300"))


settings = Settings()
