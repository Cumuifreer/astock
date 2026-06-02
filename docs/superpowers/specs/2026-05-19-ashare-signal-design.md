# A-Share Signal Design

## Goal

A-Share Signal is a private A-share technical analysis workbench. It stores market data locally, lets the user update data and run analysis as separate background tasks, and preserves state across page refreshes and service restarts.

## Architecture

The app is a FastAPI backend with a DuckDB warehouse and a Vite React frontend served by the backend in production. The backend owns all durable business state: data coverage, source health, strategy presets, task runs, analysis runs, funnel stats, warnings, and candidates. The frontend only renders API state and keeps unsaved form edits in memory.

## Data Sources

Tushare is the only external market-data source. It provides historical daily data, adjustment factors, realtime daily snapshots, daily metrics, technical factors, money flow, limit events, chip data, concept membership, and Dragon Tiger List data when the account has permission.

DuckDB is the local cache and analysis store. Pages read cached market data, task state, and diagnostics from DuckDB when a page refreshes, the service restarts, or Tushare is temporarily unavailable.

## Data Model

DuckDB stores normalized stock basics, historical bars, snapshots, float market values, source status, data capabilities, strategy presets, task runs, analysis runs, funnel stats, candidate results, and warnings. Writes use idempotent upserts and a process-level write lock. The database lives in `data/ashare_signal.duckdb` by default and is ignored by Git.

## Task Flow

Data update and analysis are separate background tasks. Starting a task immediately returns a task id. The status endpoints expose stage, Tushare sync status, current stock, totals, success, failure, skipped counts, warnings, and summary. Analysis reads only local DuckDB data and never calls external sources.

## Strategy

Strategies are JSON configs persisted as named presets. The system seeds default presets, and the user can create, update, duplicate, delete custom presets, set a default, restore system defaults, and save-and-run.

## Indicators

Amplitude is computed from local K-lines as `(high - low) / prev_close`. RPS20, RPS60, and RPS120 are computed from local close-price returns and ranked by percentile across the current stock universe. Turnover and float market value come from cached Tushare fields when synced; missing values can skip or relax the affected strategy filter.

## Frontend

The UI is a dark, compact financial terminal with teal and lime accents, dense tables, precise cards, status chips, and no developer-facing engineering copy. Pages: overview, warehouse, strategy, candidates, data map, and run status.

## Deployment

The backend can initialize or migrate DuckDB safely, serve frontend `dist`, and run under a single `uvicorn` command or systemd service. `git pull`, backend dependency installation, frontend build, migration, and restart are documented in README.
