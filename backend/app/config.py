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


settings = Settings()
