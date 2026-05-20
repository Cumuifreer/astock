# A-Share Signal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a durable A-share technical analysis web app with local DuckDB storage, protected data-source updates, background analysis, strategy presets, and a polished dark financial UI.

**Architecture:** FastAPI exposes API and serves Vite React static assets. DuckDB persists all business state. Data source adapters normalize Baostock, AkShare Sina, AkShare Tencent, AData, and local cache into the same tables; task services keep update and analysis status durable.

**Tech Stack:** Python 3.11+, FastAPI, DuckDB, Pandas, Baostock, AkShare, optional AData, Vite, React, TypeScript, lucide-react.

---

### Task 1: Project Skeleton

**Files:**
- Create: `requirements.txt`
- Create: `package.json`
- Create: `backend/app/main.py`
- Create: `frontend/src/App.tsx`

- [x] Initialize Git repository on `main`.
- [x] Create backend, frontend, docs, scripts, and data directories.
- [ ] Add dependency manifests and app entry points.

### Task 2: Warehouse And Tests

**Files:**
- Create: `backend/app/db.py`
- Create: `backend/app/config.py`
- Create: `backend/app/schema.py`
- Create: `backend/tests/test_indicators.py`
- Create: `backend/tests/test_code_normalization.py`

- [ ] Write failing tests for code normalization, amplitude, RPS, and strategy filtering.
- [ ] Implement schema migration and idempotent upsert helpers.
- [ ] Seed default strategy presets.

### Task 3: Data Sources And Update Task

**Files:**
- Create: `backend/app/sources/base.py`
- Create: `backend/app/sources/baostock_source.py`
- Create: `backend/app/sources/akshare_source.py`
- Create: `backend/app/sources/adata_source.py`
- Create: `backend/app/services/update_service.py`

- [ ] Implement cache-first source guard with TTL, backoff, jitter, and source status persistence.
- [ ] Implement Baostock historical/basics update with front-adjusted data and turnover.
- [ ] Implement AkShare Sina snapshot update and AkShare Tencent dynamic fallback.
- [ ] Implement optional AData fallback and enrichment.
- [ ] Persist detailed task status and capability coverage.

### Task 4: Analysis And API

**Files:**
- Create: `backend/app/services/analysis_service.py`
- Create: `backend/app/services/strategy_service.py`
- Create: `backend/app/api/routes.py`

- [ ] Implement analysis from local DuckDB only.
- [ ] Persist analysis runs, funnel stats, candidates, and zero-candidate explanations.
- [ ] Implement health, bootstrap, data overview, data capabilities, task status, candidates, and strategy APIs.

### Task 5: Frontend Workbench

**Files:**
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/styles.css`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/types.ts`

- [ ] Build pages for overview, warehouse, strategy, candidates, data map, and run status.
- [ ] Poll running task status without blocking the UI.
- [ ] Support strategy create/save/save-as/duplicate/delete/default/reset/save-and-run.
- [ ] Show clear empty, partial-success, warning, and API-error states.

### Task 6: Deployment And Verification

**Files:**
- Create: `README.md`
- Create: `.gitignore`
- Create: `scripts/init_db.py`
- Create: `scripts/backup_db.py`

- [ ] Document Ubuntu deployment, frontend build, backend startup, migrations, backup, and systemd.
- [ ] Verify Python compile, migration, key APIs, frontend install/build, backend static serving, banned-source absence, and source detection.
- [ ] Commit and push to `main`.
