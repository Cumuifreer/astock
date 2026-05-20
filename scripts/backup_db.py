from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import settings


def main() -> None:
    source = settings.db_path
    if not source.exists():
        raise SystemExit(f"database not found: {source}")
    backup_dir = settings.data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"ashare_signal_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.duckdb"
    shutil.copy2(source, target)
    print(target)


if __name__ == "__main__":
    main()
