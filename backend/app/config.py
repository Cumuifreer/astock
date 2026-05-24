from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


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
    public_source_min_delay: float = float(os.getenv("ASHARE_PUBLIC_SOURCE_MIN_DELAY", "0.8"))
    public_source_max_delay: float = float(os.getenv("ASHARE_PUBLIC_SOURCE_MAX_DELAY", "2.2"))
    intraday_scheduler_enabled: bool = os.getenv("ASHARE_INTRADAY_SCHEDULER", "1") == "1"
    intraday_scheduler_poll_seconds: int = int(os.getenv("ASHARE_INTRADAY_SCHEDULER_POLL_SECONDS", "30"))
    intraday_scheduler_catchup_minutes: int = int(os.getenv("ASHARE_INTRADAY_SCHEDULER_CATCHUP_MINUTES", "8"))
    daily_brief_scheduler_enabled: bool = os.getenv("ASHARE_DAILY_BRIEF_SCHEDULER", "1") == "1"
    daily_brief_scheduler_poll_seconds: int = int(os.getenv("ASHARE_DAILY_BRIEF_POLL_SECONDS", "60"))
    daily_brief_schedule_time: str = os.getenv("ASHARE_DAILY_BRIEF_TIME", "08:20")
    daily_brief_source_timeout_seconds: int = int(os.getenv("ASHARE_DAILY_BRIEF_SOURCE_TIMEOUT", "12"))
    daily_brief_api_key: str = os.getenv("ASHARE_DAILY_BRIEF_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
    daily_brief_model: str = os.getenv("ASHARE_DAILY_BRIEF_MODEL", "v4-flash")
    daily_brief_llm_url: str = os.getenv("ASHARE_DAILY_BRIEF_LLM_URL", "https://api.deepseek.com/chat/completions")


settings = Settings()
