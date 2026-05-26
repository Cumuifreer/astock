# Intraday Radar 10-Minute Cadence and Tushare Data Design

## Goal

Upgrade the intraday radar from a sparse fixed-time sampler to a Tushare-first, 10-minute intraday workflow. The change should improve signal freshness without bloating the UI or database, and it should remove AData completely from the active codebase.

## Scope

This design covers:

- 10-minute intraday sampling schedule.
- One shared schedule source for the script, backend scheduler, runtime health API, and frontend display.
- A compressed frontend schedule display for dense intraday slots.
- Post-history cleanup of intraday snapshot storage.
- Complete removal of AData integrations.
- Tushare data expansion plan and data map coverage updates.

This design does not implement all Tushare enrichment data in the first code pass. The first pass prepares the cadence, cleanup, source removal, and data map structure. Tushare enrichment should then land in staged follow-up work.

## Intraday Schedule

The new default schedule is:

`09:35,09:45,09:55,10:05,10:15,10:25,10:35,10:45,10:55,11:05,11:15,11:25,13:00,13:10,13:20,13:30,13:40,13:50,14:00,14:10,14:20,14:30,14:40,14:50,14:55`

The environment variable `ASHARE_INTRADAY_SCHEDULE` becomes the single source of truth. A shared parser should normalize this value into sorted `(hour, minute)` pairs. The following consumers should use it:

- `scripts/run_intraday_snapshot.py`
- `backend.app.services.intraday_scheduler.IntradayScheduler`
- `backend.app.services.data_service.DataService.runtime_health`
- Frontend intraday/status pages through the runtime health API, not through hardcoded frontend constants.

The scheduler still deduplicates by deterministic task IDs such as `intraday-auto-YYYYMMDD-HHMM`.

## Frontend Schedule Display

The dense 10-minute schedule should not render as a long uninterrupted strip in the primary radar view.

The intraday page should show:

- Latest sampled slot.
- Next slot.
- Remaining slots today.
- A compact rolling window around the latest/next slot.

Example:

`最近 10:35 · 下次 10:45 · 今日还剩 15 次`

The compact row can show the previous two slots, latest slot, next slot, next one or two pending slots, then a `+N` summary. The status page may still offer the full slot list, but should prefer the same compressed display by default or make the full list visually secondary.

## Intraday Snapshot Retention

Increasing from 10 samples/day to 25 samples/day makes retention important.

After the daily light historical K-line update succeeds, cleanup should remove intraday-only rows for trading days that have already been committed to `historical_bars`.

Cleanup targets:

- `intraday_snapshots`
- `intraday_radar_candidates`
- `intraday_radar_rankings`

Default behavior:

- Keep today's intraday rows.
- Keep recent intraday rows for a short review window.
- Delete older intraday rows once the same trade date exists in `historical_bars`.

The review window should be configurable through `ASHARE_INTRADAY_RETENTION_DAYS`, with a conservative default of 10 calendar days. A value of `0` deletes all eligible historical intraday rows after daily history is updated, while a negative value disables cleanup.

`daily_snapshots` should not be the primary cleanup target. It stores one row per stock per date and is reused by analysis and health checks.

## Source Strategy

Tushare becomes the primary source for intraday snapshots and future enrichment.

AData should be completely removed:

- Remove `backend/app/sources/adata_source.py`.
- Remove imports and fallback calls from update/probe/history/snapshot flows.
- Remove AData from capability fallback source labels.
- Remove package dependency if present.
- Update tests and README references.

AkShare should remain only as an emergency fallback for intraday/daily snapshots when Tushare is unavailable or unconfigured. It should not be treated as the preferred path.

Baostock should remain temporarily for historical K-line and stock basic fallback. Replacing Baostock with Tushare historical daily data is valuable, but should be done as a separate migration because historical K-line is the system's base layer.

## Tushare Enrichment Plan

Phase 1: high-confidence daily enrichment

- `daily_basic`: turnover, volume ratio, valuation, total market value, circulating market value.
- `stk_factor`: technical indicators such as MACD, KDJ, RSI, BOLL, CCI, and daily factor fields.

These should feed the data map first, then analysis/radar scoring after coverage is verified.

Phase 2: explanation and risk layer

- `moneyflow`: post-close fund flow and main-force net flow.
- `limit_list_d`: limit-up/down state, open-board count, first/last limit time, seal amount.
- `cyq_perf` and `cyq_chips`: chip pressure, winner rate, cost distribution.

These should enrich candidate explanations and risk tags before they influence hard filters.

Phase 3: market and sector context

- `ths_member`: concept/sector membership.
- Realtime index and industry K-line if available under the account permissions.
- Dragon Tiger List and hot-money data only as annotation/event context, not as the first scoring layer.

## Data Map

The data map should add rows for new Tushare-backed capabilities even before all of them participate in scoring:

- 每日指标
- 技术因子
- 资金流向
- 涨跌停
- 筹码分布
- 概念/行业成分
- 龙虎榜/游资

Each row should report:

- Coverage count.
- Missing count.
- Latest update date.
- Actual sources.
- Whether it participates in analysis.
- Whether it can be backfilled.

Existing rows should also reflect the new source strategy:

- 当天行情快照: Tushare realtime first, AkShare fallback, local cache.
- 历史 K 线: Baostock first for now, Tushare migration planned, local cache.
- 流通市值/换手率: Tushare daily_basic should become the preferred source after integration.

## Testing

Backend tests should cover:

- Schedule parser accepts valid `ASHARE_INTRADAY_SCHEDULE`, ignores malformed entries with a warning, and falls back to the default schedule if no valid entries remain.
- Scheduler and runtime health use the same parsed slots.
- 10-minute default contains 25 slots and still deduplicates task IDs.
- Cleanup removes eligible old intraday rows and preserves today's rows.
- AData imports and fallback paths are gone.
- Capabilities include the new Tushare rows.

Frontend tests or build verification should cover:

- Intraday page no longer depends on hardcoded slots.
- Compact schedule display handles dense slot lists.
- Runtime status still shows latest, next, and remaining slots.

## Rollout

Local workflow remains unchanged:

1. Edit locally on `main`.
2. Run backend tests and frontend build.
3. Commit and push.
4. Pull on the cloud server.
5. Restart the systemd service/timer as needed.

The cloud environment should set the same `ASHARE_INTRADAY_SCHEDULE` value used by the app and the timer. If the external systemd timer is used, its `OnCalendar` should match the same 10-minute schedule.
