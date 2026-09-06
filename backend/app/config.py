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

    retired_prefixes = ("ASHARE_TUSHARE", "ASHARE_LLM", "ASHARE_DAILY_BRIEF", "ASHARE_INTRADAY", "ASHARE_SINA")
    for key, value in entries.items():
        if key not in {"TUSHARE_TOKEN", "DEEPSEEK_API_KEY", "LLM_API_KEY"} and not key.startswith(retired_prefixes):
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
    default_history_days: int = int(os.getenv("ASHARE_HISTORY_DAYS", "550"))
    update_limit: int = int(os.getenv("ASHARE_UPDATE_LIMIT", "0"))
    include_bj: bool = os.getenv("ASHARE_INCLUDE_BJ", "0") == "1"
    exclude_star_board: bool = os.getenv("ASHARE_EXCLUDE_STAR_BOARD", "0") == "1"
    baostock_min_delay: float = float(os.getenv("ASHARE_BAOSTOCK_MIN_DELAY", "0.12"))
    baostock_max_delay: float = float(os.getenv("ASHARE_BAOSTOCK_MAX_DELAY", "0.45"))
    baostock_socket_timeout_seconds: float = float(os.getenv("ASHARE_BAOSTOCK_SOCKET_TIMEOUT", "30"))
    baostock_max_consecutive_failures: int = int(os.getenv("ASHARE_BAOSTOCK_MAX_CONSECUTIVE_FAILURES", "8"))
    baostock_industry_refresh_days: int = int(os.getenv("ASHARE_BAOSTOCK_INDUSTRY_REFRESH_DAYS", "30"))
    public_source_min_delay: float = 0.8
    public_source_max_delay: float = 2.2
    daily_update_scheduler_enabled: bool = os.getenv("ASHARE_DAILY_UPDATE_SCHEDULER", "0") == "1"
    daily_update_scheduler_poll_seconds: int = int(os.getenv("ASHARE_DAILY_UPDATE_POLL_SECONDS", "60"))
    daily_update_schedule_time: str = os.getenv("ASHARE_DAILY_UPDATE_TIME", "18:30")
    daily_update_mode: str = "daily_light"
    analysis_batch_size: int = int(os.getenv("ASHARE_ANALYSIS_BATCH_SIZE", "200"))
    db_memory_limit: str = os.getenv("ASHARE_DB_MEMORY_LIMIT", "512MB")
    db_threads: int = int(os.getenv("ASHARE_DB_THREADS", "2"))
    # Compatibility flags for reading old saved strategies; integrations are retired.
    tushare_token: str = ""
    daily_brief_api_key: str = ""
    tushare_enabled: bool = False
    llm_enabled: bool = False
    http_basic_username: str = os.getenv("ASHARE_HTTP_BASIC_USERNAME", "").strip()
    http_basic_password: str = os.getenv("ASHARE_HTTP_BASIC_PASSWORD", "").strip()


settings = Settings()
