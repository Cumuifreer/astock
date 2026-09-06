from datetime import date
from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.update_service import UpdateService


def test_float_market_value_uses_same_day_history_without_snapshot(tmp_path):
    db = Database(tmp_path / 'test.duckdb')
    migrate(db)
    db.upsert('historical_bars', [dict(code='000001.SZ', date='2026-09-04', close=10., volume=1_000_000., turn=2.)], ['code', 'date'])
    service = UpdateService(db)
    assert service._update_float_values_from_history(date(2026, 9, 4)) == 1
    assert db.scalar('SELECT float_market_value FROM float_market_values') == 500_000_000.
    assert service._update_float_values_from_history(date(2026, 9, 3)) == 0
    service.close()
