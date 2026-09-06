import json
from contextlib import contextmanager
from datetime import date, datetime, timedelta

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.db import Database
from backend.app.schema import migrate
from backend.app.services.analysis_service import AnalysisService, _apply_strategy_rule_filters
from backend.app.services.data_service import DataService
from backend.app.services.strategy_service import DEFAULT_STRATEGY_CONFIG, StrategyService
from backend.app.services.update_service import UpdateService
from backend.app.services.watchlist_service import WatchlistService


@pytest.fixture
def db(tmp_path):
    result = Database(tmp_path / 'review.duckdb')
    migrate(result)
    return result


def bar(code='000001.SZ', day=date(2026, 9, 4), close=20.0):
    return dict(code=code, date=day, open=close, high=close + 1, low=close - 1,
                close=close, prev_close=close, volume=1_000_000., amount=200_000_000.,
                turn=2., pct_chg=0., tradestatus='1', is_st=False, source='Baostock')


def seed(db):
    db.upsert('stock_basic', [dict(code='000001.SZ', name='测试', exchange='SZ', is_st=False, suspended=False, updated_at=datetime.utcnow())], ['code'])
    db.upsert('historical_bars', [bar()], ['code', 'date'])


@pytest.mark.parametrize('snapshot_date', ['2026-08-25', '2026-09-04', '2026-09-05'])
def test_screening_uses_daily_bar_even_with_conflicting_snapshot(db, snapshot_date):
    seed(db)
    db.upsert('daily_snapshots', [dict(code='000001.SZ', date=snapshot_date, latest_price=5., volume=1., amount=1., turnover_rate=50., pct_chg=-10.)], ['code', 'date'])
    frame = AnalysisService(db)._build_analysis_frame(DEFAULT_STRATEGY_CONFIG)
    row = frame.iloc[0]
    assert row['bar_date'] == '2026-09-04'
    assert row['latest_price'] == 20.
    assert row['amount'] == 200_000_000.
    assert row['float_market_value'] == 1_000_000_000.
    assert row['data_sources']['float_market_value'] == '本地历史换手率估算'


def test_report_and_watchlist_use_market_date_not_execution_date(db):
    seed(db)
    run_id = AnalysisService(db).run(DEFAULT_STRATEGY_CONFIG)
    report = DataService(db).analysis_report(run_id)
    assert report['analysis']['summary']['trade_date'] == '2026-09-04'
    assert len(report['candidates']['rows']) == 1
    watchlist = WatchlistService(db)
    watchlist.add_items(dict(source_type='strategy', source_ref=run_id, items=[dict(code='000001.SZ', entry_price=20.)]))
    assert watchlist.result()['batches'][0]['items'][0]['entry_date'] == date(2026, 9, 4)


def test_historical_flags_do_not_change_when_stock_basic_changes(db):
    seed(db)
    service = AnalysisService(db)
    before = service._build_analysis_frame(DEFAULT_STRATEGY_CONFIG, as_of_date=date(2026, 9, 4))
    db.upsert('stock_basic', [dict(code='000001.SZ', is_st=True, suspended=True)], ['code'])
    after = service._build_analysis_frame(DEFAULT_STRATEGY_CONFIG, as_of_date=date(2026, 9, 4))
    assert before.iloc[0]['latest_price'] == after.iloc[0]['latest_price']
    assert not bool(after.iloc[0]['is_st'])
    assert not bool(after.iloc[0]['suspended'])


def test_rps_universe_excludes_stale_stock(db):
    target = date(2026, 9, 4)
    rows = [bar(code=code, day=target - timedelta(days=offset + i), close=10. + (21-i) * speed)
            for code, offset, speed in [('000001.SZ', 0, 1), ('000002.SZ', 1, 100)] for i in range(21)]
    db.upsert('historical_bars', rows, ['code', 'date'])
    scores = AnalysisService(db)._compute_rps_scores_from_db(target, windows=(20,))
    assert scores == {'000001.SZ': {'rps20': 100.}}


@pytest.mark.parametrize('policy,expected_count', [('skip', 0), ('allow', 1)])
def test_missing_filter_column_obeys_explicit_policy(policy, expected_count):
    frame = pd.DataFrame([dict(code='000001.SZ')])
    config = dict(strategy_rules=[dict(id='r', indicator_id='rps20', action='filter', operator='gte', value=80, enabled=True, missing_policy=policy)])
    result = _apply_strategy_rule_filters(frame, config, [])
    assert len(result) == expected_count


def test_batch_upsert_preserves_types_nulls_and_last_duplicate(db):
    db.execute('CREATE TABLE bulk_test (id INTEGER PRIMARY KEY, flag BOOLEAN, day DATE, payload TEXT, value DOUBLE)', write=True)
    rows = [dict(id=1, flag=True, day=date(2026, 9, 4), payload={'a': 1}, value=2.),
            dict(id=2, flag=False, day=None, payload={'b': 2}, value=None),
            dict(id=1, flag=False, day=date(2026, 9, 5), payload={'a': 3}, value=0.)]
    assert db.upsert('bulk_test', rows, ['id']) == 3
    result = db.query('SELECT * FROM bulk_test ORDER BY id')
    assert result[0] == dict(id=1, flag=False, day=date(2026, 9, 5), payload='{"a": 3}', value=0.)
    assert result[1]['value'] is None
    db.upsert('bulk_test', [dict(id=1, value=None), dict(id=2, value=8.)], ['id'])
    assert db.scalar('SELECT value FROM bulk_test WHERE id=1') is None
    assert db.scalar('SELECT flag FROM bulk_test WHERE id=1') is False


def test_batch_upsert_rolls_back_when_one_row_is_invalid(db):
    db.execute('CREATE TABLE checked_test (id INTEGER PRIMARY KEY, value INTEGER CHECK (value >= 0))', write=True)
    db.upsert('checked_test', [dict(id=1, value=10)], ['id'])
    with pytest.raises(Exception):
        db.upsert('checked_test', [dict(id=1, value=20), dict(id=2, value=-1)], ['id'])
    assert db.query('SELECT * FROM checked_test') == [dict(id=1, value=10)]


def test_daily_update_needs_no_snapshot_or_paid_service(db, monkeypatch):
    from backend.app.services import update_service
    target = date(2026, 9, 4)
    class Source:
        @contextmanager
        def session(self):
            yield self
        def fetch_trade_calendar(self, *args, **kwargs):
            return pd.DataFrame([dict(date=target, is_trading_day=True)])
        def fetch_stock_basics(self, **kwargs):
            return pd.DataFrame([dict(code='000001.SZ', name='测试', exchange='SZ', is_st=False, suspended=False, updated_at=datetime.utcnow())])
        def fetch_stock_industry(self, **kwargs):
            return pd.DataFrame()
        def fetch_history(self, code, start, end, **kwargs):
            return pd.DataFrame([bar(code, target)])
    service = UpdateService(db)
    monkeypatch.setattr(update_service, 'BaostockSource', Source)
    monkeypatch.setattr(service, '_target_history_date', lambda: target)
    monkeypatch.setattr(service.baostock_guard, 'sleep', lambda: None)
    monkeypatch.setattr(service, '_update_baostock_industry', lambda **kwargs: 0)
    service._write_task('update-test', kind='update', status='running')
    service._run_update('update-test', dict(mode='daily_light'))
    task = DataService(db).latest_task('update')
    assert task['status'] == 'completed_full'
    assert task['summary']['covered_count'] == 1
    assert db.scalar('SELECT COUNT(*) FROM daily_snapshots') == 0
    assert db.scalar('SELECT COUNT(*) FROM historical_bars') == 1
    assert db.scalar('SELECT float_market_value FROM float_market_values') == 1_000_000_000.
    service.close()


def test_analysis_task_creates_no_ai_jobs(db):
    seed(db)
    service = UpdateService(db)
    service._write_task('analyze-test', kind='analyze', status='running')
    service._run_analysis('analyze-test', DEFAULT_STRATEGY_CONFIG, AnalysisService(db))
    assert DataService(db).latest_task('analyze')['status'] == 'completed_full'
    assert db.scalar('SELECT COUNT(*) FROM task_runs') == 1
    assert db.scalar('SELECT COUNT(*) FROM candidate_ai_summaries') == 0
    service.close()


def test_api_bootstrap_is_config_only_and_retired_routes_are_absent(db, monkeypatch):
    from backend.app.api import routes
    seed(db)
    monkeypatch.setattr(routes, 'db', db)
    monkeypatch.setattr(routes, 'data_service', DataService(db))
    monkeypatch.setattr(routes, 'strategy_service', StrategyService(db))
    monkeypatch.setattr(routes, 'watchlist_service', WatchlistService(db))
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    response = client.get('/api/bootstrap')
    assert response.status_code == 200
    assert set(response.json()) == {'indicator_library', 'strategies', 'default_strategy'}
    assert client.get('/api/review/overview').json()['covered_count'] == 1
    assert client.get('/api/watchlist/codes').json() == {'codes': []}
    for path in ['/api/tasks/candidate-ai-summary', '/api/tasks/intraday-snapshot', '/api/backtest/portfolio', '/api/daily-brief/regenerate']:
        assert client.post(path, json={}).status_code == 404
    assert client.post('/api/tasks/update', json={'mode': 'market_environment'}).status_code == 400
