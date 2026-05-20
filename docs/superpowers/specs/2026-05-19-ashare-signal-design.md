# A-Share Signal Design

## Goal

A-Share Signal is a private A-share technical analysis workbench. It stores market data locally, lets the user update data and run analysis as separate background tasks, and preserves state across page refreshes and service restarts.

## Architecture

The app is a FastAPI backend with a DuckDB warehouse and a Vite React frontend served by the backend in production. The backend owns all durable business state: data coverage, source health, strategy presets, task runs, analysis runs, funnel stats, warnings, and candidates. The frontend only renders API state and keeps unsaved form edits in memory.

## Data Sources

Baostock is the historical K-line primary source and provides front-adjusted bars, turnover, ST status, suspension status, volume, and amount. AkShare Sina is the main full-market snapshot source. AkShare Tencent is detected dynamically and used as a snapshot fallback when the installed AkShare version exposes a compatible Tencent snapshot interface; otherwise its unavailable reason is persisted and displayed. AData is optional and participates as a fallback for stock basics, historical bars, snapshots, and float-market-value enrichment when installed and non-empty.

No EM-related market source is called directly or listed as a source.

## Data Model

DuckDB stores normalized stock basics, historical bars, snapshots, float market values, source status, data capabilities, strategy presets, task runs, analysis runs, funnel stats, candidate results, and warnings. Writes use idempotent upserts and a process-level write lock. The database lives in `data/ashare_signal.duckdb` by default and is ignored by Git.

## Task Flow

Data update and analysis are separate background tasks. Starting a task immediately returns a task id. The status endpoints expose stage, source, current stock, totals, success, failure, skipped counts, warnings, and summary. Analysis reads only local DuckDB data and never calls external sources.

## Strategy

Strategies are JSON configs persisted as named presets. The system seeds default presets, and the user can create, update, duplicate, delete custom presets, set a default, restore system defaults, and save-and-run.

## Indicators

Amplitude is computed from local K-lines as `(high - low) / prev_close`. RPS20, RPS60, and RPS120 are computed from local close-price returns and ranked by percentile across the current stock universe. Turnover comes from Baostock `turn`, with missing coverage tracked and displayed. Float market value comes from local cache first and AData-derived float shares times latest price when available; missing values can skip or relax market-cap filtering by strategy.

## Frontend

The UI is a dark, compact financial terminal with teal and lime accents, dense tables, precise cards, status chips, and no developer-facing engineering copy. Pages: overview, warehouse, strategy, candidates, data map, and run status.

## Deployment

The backend can initialize or migrate DuckDB safely, serve frontend `dist`, and run under a single `uvicorn` command or systemd service. `git pull`, backend dependency installation, frontend build, migration, and restart are documented in README.
