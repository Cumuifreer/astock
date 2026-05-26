# Intraday Tushare Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Move the intraday radar to a Tushare-first 10-minute cadence, compact the frontend schedule display, prune old intraday storage, remove AData, and prepare the data map for the next Tushare enrichment phases.

**Architecture:** Add one backend schedule helper as the single schedule source for settings, scheduler, runtime health, and script checks. Keep Tushare realtime daily as the primary intraday source, with AkShare only as emergency fallback. Add retention cleanup inside the daily update flow after historical bars are updated, and expose compact schedule data through the existing runtime health API.

**Tech Stack:** Python 3.11, FastAPI service layer, DuckDB, Pandas, pytest, Vite, React, TypeScript, lucide-react.

---

## File Structure

- Create `backend/app/services/intraday_schedule.py`: parse `ASHARE_INTRADAY_SCHEDULE`, hold the 10-minute default, and provide compact schedule utilities for backend consumers.
- Modify `backend/app/config.py`: add `intraday_schedule` and `intraday_retention_days`.
- Modify `backend/app/services/intraday_scheduler.py`: consume parsed slots instead of a local hardcoded tuple.
- Modify `backend/app/services/data_service.py`: consume parsed slots, add schedule summary fields, add Tushare capability rows, and remove AData fallback labels.
- Modify `backend/app/services/update_service.py`: remove AData fallbacks and call retention cleanup after successful history update.
- Modify `scripts/run_intraday_snapshot.py`: share the default schedule text and parser-compatible behavior.
- Delete `backend/app/sources/adata_source.py`.
- Modify `requirements.txt`: remove `adata`.
- Modify `frontend/src/types.ts`: add schedule summary fields to `RuntimeHealth.scheduler`.
- Modify `frontend/src/App.tsx`: remove hardcoded intraday slots and render compact schedule windows from runtime health.
- Modify `frontend/src/styles.css`: add compact schedule summary/window styles.
- Modify `README.md`: update Tushare/AkShare/AData wording, 10-minute schedule, cleanup, and systemd timer notes.
- Modify tests in `backend/tests/test_intraday_scheduler.py`, `backend/tests/test_intraday_radar_service.py`, and `backend/tests/test_data_warehouse.py`.

---

### Task 1: Shared Intraday Schedule Parser

**Files:**
- Create: `backend/app/services/intraday_schedule.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/services/intraday_scheduler.py`
- Test: `backend/tests/test_intraday_scheduler.py`

- [x] **Step 1: Write failing parser tests**

Add these tests to `backend/tests/test_intraday_scheduler.py`:

```python
from backend.app.services.intraday_schedule import DEFAULT_INTRADAY_SCHEDULE_TEXT, parse_intraday_schedule


def test_default_intraday_schedule_has_10_minute_slots():
    slots = parse_intraday_schedule("")

    assert len(slots) == 25
    assert slots[0] == (9, 35)
    assert slots[1] == (9, 45)
    assert slots[-2:] == [(14, 50), (14, 55)]
    assert DEFAULT_INTRADAY_SCHEDULE_TEXT.startswith("09:35,09:45,09:55")


def test_intraday_schedule_parser_sorts_deduplicates_and_falls_back():
    assert parse_intraday_schedule("10:00,09:35,10:00,bad,25:99") == [(9, 35), (10, 0)]
    assert parse_intraday_schedule("bad,25:99") == parse_intraday_schedule("")
```

- [x] **Step 2: Run parser tests and verify failure**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_intraday_scheduler.py::test_default_intraday_schedule_has_10_minute_slots backend/tests/test_intraday_scheduler.py::test_intraday_schedule_parser_sorts_deduplicates_and_falls_back -q
```

Expected: fail because `backend.app.services.intraday_schedule` does not exist.

- [x] **Step 3: Add shared schedule helper**

Create `backend/app/services/intraday_schedule.py`:

```python
from __future__ import annotations

import logging
from typing import Iterable, List, Sequence, Tuple

IntradaySlot = Tuple[int, int]

DEFAULT_INTRADAY_SLOTS: Tuple[IntradaySlot, ...] = (
    (9, 35), (9, 45), (9, 55),
    (10, 5), (10, 15), (10, 25), (10, 35), (10, 45), (10, 55),
    (11, 5), (11, 15), (11, 25),
    (13, 0), (13, 10), (13, 20), (13, 30), (13, 40), (13, 50),
    (14, 0), (14, 10), (14, 20), (14, 30), (14, 40), (14, 50), (14, 55),
)
DEFAULT_INTRADAY_SCHEDULE_TEXT = ",".join(f"{hour:02d}:{minute:02d}" for hour, minute in DEFAULT_INTRADAY_SLOTS)


def parse_intraday_schedule(raw: str | None) -> List[IntradaySlot]:
    text = (raw or "").strip()
    if not text:
        return list(DEFAULT_INTRADAY_SLOTS)
    slots: set[IntradaySlot] = set()
    invalid: list[str] = []
    for item in text.split(","):
        token = item.strip()
        if not token:
            continue
        try:
            hour_text, minute_text = token.split(":", 1)
            hour = int(hour_text)
            minute = int(minute_text)
        except ValueError:
            invalid.append(token)
            continue
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            invalid.append(token)
            continue
        slots.add((hour, minute))
    if invalid:
        logging.warning("忽略无效盘中采样时间: %s", ",".join(invalid))
    return sorted(slots) if slots else list(DEFAULT_INTRADAY_SLOTS)


def format_intraday_schedule(slots: Sequence[IntradaySlot]) -> List[str]:
    return [f"{hour:02d}:{minute:02d}" for hour, minute in slots]
```

- [x] **Step 4: Wire settings and scheduler**

In `backend/app/config.py`, add:

```python
    intraday_schedule: str = os.getenv("ASHARE_INTRADAY_SCHEDULE", "")
    intraday_retention_days: int = int(os.getenv("ASHARE_INTRADAY_RETENTION_DAYS", "10"))
```

In `backend/app/services/intraday_scheduler.py`, import the shared default:

```python
from backend.app.services.intraday_schedule import DEFAULT_INTRADAY_SLOTS
```

Remove the local `DEFAULT_INTRADAY_SLOTS` tuple from that file.

- [x] **Step 5: Pass parsed slots from app startup**

In `backend/app/main.py`, import `parse_intraday_schedule` and pass parsed slots:

```python
from backend.app.services.intraday_schedule import parse_intraday_schedule

intraday_scheduler = IntradayScheduler(
    update_service,
    poll_seconds=settings.intraday_scheduler_poll_seconds,
    catchup_minutes=settings.intraday_scheduler_catchup_minutes,
    slots=parse_intraday_schedule(settings.intraday_schedule),
)
```

- [x] **Step 6: Run scheduler tests**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_intraday_scheduler.py -q
```

Expected: pass.

---

### Task 2: Runtime Health Uses the Shared Schedule

**Files:**
- Modify: `backend/app/services/data_service.py`
- Modify: `backend/app/api/routes.py`
- Modify: `frontend/src/types.ts`
- Test: `backend/tests/test_intraday_scheduler.py`

- [x] **Step 1: Write failing runtime health assertions**

Update `test_runtime_health_reports_scheduler_slots_and_data_dates` to assert shared slots and summary:

```python
    assert len(health["scheduler"]["slots"]) == 25
    assert health["scheduler"]["slot_count"] == 25
    assert health["scheduler"]["completed_count"] >= 0
    assert health["scheduler"]["remaining_count"] == 0
    assert health["scheduler"]["latest_slot"]["time"] == "14:55"
```

- [x] **Step 2: Run the test and verify failure**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_intraday_scheduler.py::test_runtime_health_reports_scheduler_slots_and_data_dates -q
```

Expected: fail because runtime health still uses the old hardcoded tuple and has no summary fields.

- [x] **Step 3: Update runtime health signature**

In `backend/app/services/data_service.py`, remove the local `DEFAULT_INTRADAY_SLOTS`, import parser:

```python
from backend.app.services.intraday_schedule import parse_intraday_schedule
```

Update `runtime_health` signature:

```python
    def runtime_health(
        self,
        now: Optional[datetime] = None,
        scheduler_enabled: bool = True,
        poll_seconds: int = 30,
        catchup_minutes: int = 8,
        schedule: str = "",
    ) -> Dict[str, Any]:
```

Then replace:

```python
        for hour, minute in DEFAULT_INTRADAY_SLOTS:
```

with:

```python
        for hour, minute in parse_intraday_schedule(schedule):
```

- [x] **Step 4: Add scheduler summary fields**

Before returning `scheduler`, compute:

```python
        completed_slots = [slot for slot in slots if slot["status"] in {"completed_full", "completed_partial", "queued", "running"}]
        latest_slot = completed_slots[-1] if completed_slots else None
        remaining_count = len([slot for slot in slots if slot["status"] in {"pending", "due"}])
```

Add fields to the returned scheduler dict:

```python
                "slot_count": len(slots),
                "completed_count": len(completed_slots),
                "remaining_count": remaining_count,
                "latest_slot": latest_slot,
```

- [x] **Step 5: Pass schedule through API routes**

In `backend/app/api/routes.py`, pass `settings.intraday_schedule` in both `runtime_health` calls:

```python
            schedule=settings.intraday_schedule,
```

- [x] **Step 6: Update frontend type**

In `frontend/src/types.ts`, extend `RuntimeHealth.scheduler`:

```ts
    slot_count: number;
    completed_count: number;
    remaining_count: number;
    latest_slot: RuntimeSlot | null;
```

- [x] **Step 7: Run scheduler tests**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_intraday_scheduler.py -q
```

Expected: pass.

---

### Task 3: Compact Frontend Schedule Display

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Verify: `npm --prefix frontend run build`

- [x] **Step 1: Replace hardcoded intraday page slots**

Change `IntradayRadarPage` to pass runtime scheduler slots into `IntradaySlotTimeline`. If `runtime` is not currently passed to the page, add `runtime={bootstrap.runtime_health}` where the page is rendered and add it to the component props.

The timeline signature should become:

```tsx
function IntradaySlotTimeline({ slots, task }: { slots: RuntimeSlot[]; task: TaskRun | null }) {
```

Remove `const INTRADAY_RADAR_SLOTS = ...`.

- [x] **Step 2: Add compact slot window helper**

Add near the timeline component:

```tsx
function compactSlotWindow(slots: RuntimeSlot[]) {
  const nextIndex = slots.findIndex((slot) => slot.status === 'pending' || slot.status === 'due');
  const latestIndex = Math.max(
    0,
    slots.reduce((last, slot, index) => (slot.status === 'completed_full' || slot.status === 'completed_partial' || slot.status === 'queued' || slot.status === 'running' ? index : last), -1),
  );
  const anchor = nextIndex >= 0 ? nextIndex : latestIndex;
  const start = Math.max(0, anchor - 2);
  const end = Math.min(slots.length, anchor + 3);
  return {
    rows: slots.slice(start, end),
    hiddenBefore: start,
    hiddenAfter: Math.max(0, slots.length - end),
    nextSlot: nextIndex >= 0 ? slots[nextIndex] : null,
    latestSlot: latestIndex >= 0 ? slots[latestIndex] : null,
    remaining: slots.filter((slot) => slot.status === 'pending' || slot.status === 'due').length,
  };
}
```

- [x] **Step 3: Render summary and compact row**

Inside `IntradaySlotTimeline`, render:

```tsx
  const compact = compactSlotWindow(slots);
  return (
    <div className="intraday-slot-panel">
      <div className="slot-summary">
        <span>最近 <b>{compact.latestSlot?.time || '-'}</b></span>
        <span>下次 <b>{compact.nextSlot?.time || '-'}</b></span>
        <span>今日还剩 <b>{formatInt(compact.remaining)}</b> 次</span>
      </div>
      <div className="slot-grid intraday-slot-grid compact" aria-label="盘中雷达时间轴">
        {compact.hiddenBefore ? <span className="slot-card muted">+{formatInt(compact.hiddenBefore)}</span> : null}
        {compact.rows.map((slot) => (
          <span key={slot.time} className={`slot-card ${slot.status} ${compact.nextSlot?.time === slot.time ? 'next' : ''}`}>
            <i />
            <b>{slot.time}</b>
            <em>{slotStatusLabel(slot.status)}</em>
            <small>{slot.sample_count ? `${formatInt(slot.sample_count)} 样本` : slot.task_status ? statusLabel(slot.task_status) : '-'}</small>
          </span>
        ))}
        {compact.hiddenAfter ? <span className="slot-card muted">+{formatInt(compact.hiddenAfter)}</span> : null}
      </div>
    </div>
  );
```

- [x] **Step 4: Compact status page slot rendering**

In `RuntimeHealthPanel`, use the same `compactSlotWindow(runtime.scheduler.slots)` and render the compact row by default. Keep the summary pill based on `runtime.scheduler.next_slot`.

- [x] **Step 5: Add CSS**

Add to `frontend/src/styles.css`:

```css
.intraday-slot-panel {
  display: grid;
  gap: 10px;
}

.slot-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--muted);
  font-size: 12px;
}

.slot-summary span {
  border: 1px solid rgba(157, 196, 187, 0.16);
  border-radius: 6px;
  padding: 6px 8px;
  background: rgba(255, 255, 255, 0.03);
}

.slot-summary b {
  color: var(--text);
}

.slot-grid.compact {
  grid-template-columns: repeat(auto-fit, minmax(86px, 1fr));
}
```

- [x] **Step 6: Build frontend**

Run:

```bash
npm --prefix frontend run build
```

Expected: Vite build succeeds.

---

### Task 4: Intraday Snapshot Retention Cleanup

**Files:**
- Modify: `backend/app/services/update_service.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_intraday_radar_service.py`

- [x] **Step 1: Write cleanup test**

Add a test that seeds old and recent intraday rows, seeds matching `historical_bars`, calls cleanup, and verifies only eligible old rows are deleted:

```python
def test_intraday_cleanup_deletes_old_rows_after_history_exists(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    old_sample = datetime(2026, 5, 10, 10, 0)
    recent_sample = datetime(2026, 5, 24, 10, 0)
    for sample_at in [old_sample, recent_sample]:
        db.upsert(
            "intraday_snapshots",
            [{
                "code": "000001.SZ",
                "trade_date": sample_at.date(),
                "sample_at": sample_at,
                "name": "平安银行",
                "latest_price": 10.0,
                "pct_chg": 1.0,
                "high": 10.2,
                "low": 9.9,
                "volume": 100,
                "amount": 1000000,
                "source": "test",
                "created_at": sample_at,
            }],
            ["code", "sample_at"],
        )
        db.upsert(
            "intraday_radar_rankings",
            [{
                "sample_at": sample_at,
                "radar_mode": "score",
                "trade_date": sample_at.date(),
                "rank": 1,
                "code": "000001.SZ",
                "name": "平安银行",
                "status": "test",
                "radar_score": 80,
                "latest_price": 10.0,
                "pct_chg": 1.0,
                "amount": 1000000,
                "volume": 100,
                "distance_to_upper": 0,
                "breakout_clearance": 0,
                "amount_delta": 0,
                "volume_delta": 0,
                "amount_ratio": 1,
                "price_change": 0,
                "source": "test",
                "reasons_json": "[]",
                "metrics_json": "{}",
                "created_at": sample_at,
            }],
            ["sample_at", "radar_mode", "code"],
        )
    db.upsert(
        "historical_bars",
        [{
            "code": "000001.SZ",
            "date": old_sample.date(),
            "open": 10,
            "high": 10,
            "low": 9,
            "close": 10,
            "prev_close": 9.8,
            "volume": 100,
            "amount": 1000000,
            "turn": 1,
            "pct_chg": 1,
            "tradestatus": "1",
            "is_st": False,
            "source": "test",
            "updated_at": old_sample,
        }],
        ["code", "date"],
    )

    deleted = service.cleanup_intraday_history(retention_days=10, now=datetime(2026, 5, 25, 8, 0))

    assert deleted["intraday_snapshots"] == 1
    assert db.scalar("SELECT COUNT(*) FROM intraday_snapshots WHERE sample_at = ?", [old_sample]) == 0
    assert db.scalar("SELECT COUNT(*) FROM intraday_snapshots WHERE sample_at = ?", [recent_sample]) == 1
    assert db.scalar("SELECT COUNT(*) FROM intraday_radar_rankings WHERE sample_at = ?", [old_sample]) == 0
```

- [x] **Step 2: Run cleanup test and verify failure**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_intraday_radar_service.py::test_intraday_cleanup_deletes_old_rows_after_history_exists -q
```

Expected: fail because `cleanup_intraday_history` does not exist.

- [x] **Step 3: Implement cleanup method**

Add to `UpdateService`:

```python
    def cleanup_intraday_history(self, retention_days: Optional[int] = None, now: Optional[datetime] = None) -> Dict[str, int]:
        keep_days = settings.intraday_retention_days if retention_days is None else retention_days
        if keep_days < 0:
            return {"intraday_snapshots": 0, "intraday_radar_candidates": 0, "intraday_radar_rankings": 0}
        current = now or datetime.now(CHINA_TZ)
        cutoff = current.date() - timedelta(days=keep_days)
        params = [cutoff]
        deleted: Dict[str, int] = {}
        for table in ["intraday_radar_rankings", "intraday_radar_candidates", "intraday_snapshots"]:
            before = self.db.scalar(f"SELECT COUNT(*) FROM {table}") or 0
            self.db.execute(
                f"""
                DELETE FROM {table}
                WHERE trade_date < ?
                  AND EXISTS (
                    SELECT 1
                    FROM historical_bars h
                    WHERE h.code = {table}.code
                      AND h.date = {table}.trade_date
                  )
                """,
                params,
            )
            after = self.db.scalar(f"SELECT COUNT(*) FROM {table}") or 0
            deleted[table] = int(before) - int(after)
        return deleted
```

- [x] **Step 4: Call cleanup after history update**

In `_run_update`, after `_update_float_values_from_snapshots()` succeeds, call:

```python
            cleanup_counts = self.cleanup_intraday_history()
```

Include `cleanup_counts` in task summary:

```python
                    "intraday_cleanup": cleanup_counts,
```

- [x] **Step 5: Run backend tests for update/intraday**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_intraday_radar_service.py backend/tests/test_daily_light_update.py -q
```

Expected: pass.

---

### Task 5: Remove AData From Active Codebase

**Files:**
- Delete: `backend/app/sources/adata_source.py`
- Modify: `backend/app/services/update_service.py`
- Modify: `backend/app/services/data_service.py`
- Modify: `requirements.txt`
- Modify: `README.md`
- Test: `backend/tests/test_intraday_radar_service.py`

- [x] **Step 1: Remove imports and probe entries**

In `backend/app/services/update_service.py`, remove:

```python
from backend.app.sources.adata_source import ADataSource
```

Remove AData tuples from `probe_sources`.

- [x] **Step 2: Remove AData fallback from snapshots**

In `_fetch_intraday_snapshot_frame`, after Tencent fails, raise from the chosen AkShare result:

```python
        if chosen.status != "available":
            raise RuntimeError(chosen.message or "盘中快照不可用。")
```

In `_update_snapshots`, after Tencent fails, return cached rows if present:

```python
        if chosen.status != "available":
            if chosen.message:
                warnings.append(f"快照全部降级到本地缓存：{chosen.message}")
            return int(today_rows)
```

- [x] **Step 3: Remove AData from basics/history**

In `_update_basics`, remove the AData stock basic fallback call. If Baostock fails, keep existing stock basics from local cache and record the Baostock failure.

In `_update_history`, remove the AData fallback block. If Baostock fetch fails, increment `failed` and record the Baostock failure message.

- [x] **Step 4: Remove AData capability labels and dependency**

In `backend/app/services/data_service.py`, remove AData from fallback source arrays:

```python
"历史 K 线": ["Baostock", "本地缓存"]
"当天行情快照": ["Tushare 实时日线", "AkShare 新浪", "AkShare 腾讯", "本地缓存"]
"股票基础信息": ["Baostock", "AkShare 快照", "本地缓存"]
"流通市值": ["Tushare daily_basic", "AkShare 新浪", "本地缓存"]
```

In `requirements.txt`, delete:

```text
adata>=2.9.5,<3
```

- [x] **Step 5: Delete AData adapter**

Delete:

```text
backend/app/sources/adata_source.py
```

- [x] **Step 6: Update Tushare preference test**

In `test_intraday_snapshot_prefers_tushare_realtime`, keep asserting Tushare is called first. Add:

```python
    assert frame.iloc[0]["source"] == "Tushare 实时日线"
```

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_intraday_radar_service.py -q
```

Expected: pass.

- [x] **Step 7: Search active code for AData**

Run:

```bash
rg -n "AData|adata" README.md requirements.txt backend frontend scripts --glob '!frontend/dist/**'
```

Expected: no output.

---

### Task 6: Data Map Tushare Capability Rows

**Files:**
- Modify: `backend/app/services/data_service.py`
- Modify: `frontend/src/App.tsx`
- Test: `backend/tests/test_data_warehouse.py`

- [x] **Step 1: Write capability test**

Add to `backend/tests/test_data_warehouse.py`:

```python
def test_capabilities_include_tushare_enrichment_layers(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    seed_stock_basics(db)

    capabilities = DataService(db).capabilities()
    by_name = {row["capability"]: row for row in capabilities}

    for name in ["每日指标", "技术因子", "资金流向", "涨跌停", "筹码分布", "概念/行业成分", "龙虎榜/游资"]:
        assert name in by_name
        assert "Tushare" in " ".join(by_name[name]["fallback_sources"])
    assert by_name["每日指标"]["participates_in_analysis"] is True
    assert by_name["龙虎榜/游资"]["participates_in_analysis"] is False
```

- [x] **Step 2: Run test and verify failure**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_data_warehouse.py::test_capabilities_include_tushare_enrichment_layers -q
```

Expected: fail because capability definitions are missing.

- [x] **Step 3: Add capability definitions**

Add these entries to `CAPABILITY_DEFINITIONS`:

```python
    "每日指标": {
        "fallback_sources": ["Tushare daily_basic"],
        "can_backfill": True,
        "participates_in_analysis": True,
    },
    "技术因子": {
        "fallback_sources": ["Tushare stk_factor"],
        "can_backfill": True,
        "participates_in_analysis": True,
    },
    "资金流向": {
        "fallback_sources": ["Tushare moneyflow"],
        "can_backfill": True,
        "participates_in_analysis": False,
    },
    "涨跌停": {
        "fallback_sources": ["Tushare limit_list_d"],
        "can_backfill": True,
        "participates_in_analysis": False,
    },
    "筹码分布": {
        "fallback_sources": ["Tushare cyq_perf", "Tushare cyq_chips"],
        "can_backfill": True,
        "participates_in_analysis": False,
    },
    "概念/行业成分": {
        "fallback_sources": ["Tushare ths_member"],
        "can_backfill": True,
        "participates_in_analysis": False,
    },
    "龙虎榜/游资": {
        "fallback_sources": ["Tushare top_list", "Tushare top_inst", "Tushare hm_detail"],
        "can_backfill": True,
        "participates_in_analysis": False,
    },
```

Add zero counts for these capabilities until ingestion exists:

```python
            "每日指标": 0,
            "技术因子": 0,
            "资金流向": 0,
            "涨跌停": 0,
            "筹码分布": 0,
            "概念/行业成分": 0,
            "龙虎榜/游资": 0,
```

- [x] **Step 4: Extend frontend data map metadata**

In `frontend/src/App.tsx`, add matching `dataLedgerMeta` entries:

```tsx
  每日指标: { fields: ['code', 'date', 'turnover_rate', 'volume_ratio', 'circ_mv'], expected: 'history' },
  技术因子: { fields: ['code', 'date', 'macd', 'kdj', 'rsi', 'boll'], expected: 'history' },
  资金流向: { fields: ['code', 'date', 'net_mf_amount', 'buy_lg_amount'], expected: 'history' },
  涨跌停: { fields: ['code', 'trade_date', 'limit', 'open_times', 'fd_amount'], expected: 'history' },
  筹码分布: { fields: ['code', 'trade_date', 'winner_rate', 'cost_50pct'], expected: 'history' },
  '概念/行业成分': { fields: ['code', 'ts_code', 'con_name', 'source'], expected: 'as_needed' },
  '龙虎榜/游资': { fields: ['code', 'trade_date', 'net_amount', 'hm_name'], expected: 'as_needed' },
```

- [x] **Step 5: Run data warehouse tests**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_data_warehouse.py -q
```

Expected: pass.

---

### Task 7: Docs and Full Verification

**Files:**
- Modify: `README.md`
- Verify: backend tests, frontend build, compileall, diff check

- [x] **Step 1: Update README**

Update active README sections:

- Tushare realtime is primary for intraday.
- AkShare is emergency fallback.
- AData is removed.
- Default intraday schedule is the 25-slot 10-minute schedule.
- `ASHARE_INTRADAY_SCHEDULE` is the shared schedule source.
- `ASHARE_INTRADAY_RETENTION_DAYS` controls old intraday cleanup.
- systemd `OnCalendar` example matches the 10-minute schedule.

- [x] **Step 2: Run backend tests**

Run:

```bash
PYTHONPATH=. pytest backend/tests -q
```

Expected: all tests pass.

- [x] **Step 3: Run frontend build**

Run:

```bash
npm --prefix frontend run build
```

Expected: build succeeds.

- [x] **Step 4: Run compile and whitespace checks**

Run:

```bash
python3 -m compileall backend/app scripts
git diff --check
```

Expected: compile succeeds and diff check has no output.

- [x] **Step 5: Inspect final diff and commit**

Run:

```bash
git status --short
git diff --stat
git add README.md requirements.txt scripts/run_intraday_snapshot.py backend frontend docs/superpowers/plans/2026-05-25-intraday-tushare-data.md
git commit -m "Increase intraday radar cadence"
```

Expected: commit succeeds on `main`.
