# Inactive Stock Label Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `非活跃` stock lifecycle label and make stock-based data-map coverage use the active stock universe.

**Architecture:** Reuse the existing `stock_basic.suspended` lifecycle flag as the first implementation of inactive stocks. Centralize active-stock SQL helpers in `DataService`, apply them to capability coverage and warehouse list queries, then expose active/inactive counts to React for data-map and warehouse UI copy.

**Tech Stack:** FastAPI, DuckDB SQL, pytest, Vite React + TypeScript, existing CSS.

---

## File Structure

- Modify `backend/app/services/data_service.py`
  - Add active/inactive stock helper SQL.
  - Return active/inactive counts from `overview()`.
  - Use active stocks as the denominator and stock coverage join target in `refresh_capabilities()`.
  - Add `status` filtering and inactive search fallback in `list_stocks()`.
- Modify `backend/app/api/routes.py`
  - Accept `status` query parameter on `/api/data/stocks`.
- Modify `backend/tests/test_data_warehouse.py`
  - Add tests for overview counts, capability denominator, inactive old-data exclusion, and warehouse status filtering.
- Modify `frontend/src/types.ts`
  - Extend `Overview` with `active_stock_count` and `inactive_stock_count`.
- Modify `frontend/src/api.ts`
  - Pass the new `status` filter through `api.stocks()`.
- Modify `frontend/src/App.tsx`
  - Show active stock count on overview card.
  - Pass stock counts into `DataMap`.
  - Add warehouse status filter and `非活跃` row badge.
  - Add data-map active-universe note.
- Modify `frontend/src/styles.css`
  - Style the inactive badge and data-map universe note.

## Task 1: Backend Active Universe Counts

**Files:**
- Modify: `backend/app/services/data_service.py`
- Test: `backend/tests/test_data_warehouse.py`

- [ ] **Step 1: Write failing overview test**

Append this test to `backend/tests/test_data_warehouse.py`:

```python
def test_overview_reports_active_and_inactive_stock_counts(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    seed_stock_basics(db)
    db.upsert(
        "stock_basic",
        [
            {
                "code": "000003.SZ",
                "name": "PT金田A",
                "exchange": "SZ",
                "list_date": date(1991, 7, 3),
                "source": "test",
                "is_st": False,
                "suspended": True,
                "updated_at": datetime(2026, 5, 24, 9, 0),
            }
        ],
        ["code"],
    )

    overview = DataService(db).overview()

    assert overview["stock_count"] == 5
    assert overview["active_stock_count"] == 4
    assert overview["inactive_stock_count"] == 1
    assert overview["turnover_coverage"]["total"] == 4
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_data_warehouse.py::test_overview_reports_active_and_inactive_stock_counts -q
```

Expected: FAIL with missing `active_stock_count` or old turnover denominator.

- [ ] **Step 3: Implement minimal active count helpers**

In `backend/app/services/data_service.py`, add module-level constants near `LOCAL_VOLUME_RATIO_JOIN`:

```python
ACTIVE_STOCK_FILTER = "b.suspended IS DISTINCT FROM TRUE"
INACTIVE_STOCK_FILTER = "b.suspended IS TRUE"
```

Add methods inside `DataService`:

```python
    def active_stock_count(self) -> int:
        return int(
            self.db.scalar(
                f"SELECT COUNT(*) FROM stock_basic b WHERE {ACTIVE_STOCK_FILTER}"
            )
            or 0
        )

    def inactive_stock_count(self) -> int:
        return int(
            self.db.scalar(
                f"SELECT COUNT(*) FROM stock_basic b WHERE {INACTIVE_STOCK_FILTER}"
            )
            or 0
        )
```

Update `overview()` to compute:

```python
        stock_count = self.db.scalar("SELECT COUNT(*) FROM stock_basic") or 0
        active_stock_count = self.active_stock_count()
        inactive_stock_count = self.inactive_stock_count()
```

and return:

```python
            "stock_count": stock_count,
            "active_stock_count": active_stock_count,
            "inactive_stock_count": inactive_stock_count,
```

Change turnover denominator in `overview()` from all stocks to `active_stock_count`.

- [ ] **Step 4: Run test to verify GREEN**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_data_warehouse.py::test_overview_reports_active_and_inactive_stock_counts -q
```

Expected: PASS.

## Task 2: Data Map Uses Active Stock Denominator

**Files:**
- Modify: `backend/app/services/data_service.py`
- Test: `backend/tests/test_data_warehouse.py`

- [ ] **Step 1: Write failing capability tests**

Append these tests to `backend/tests/test_data_warehouse.py`:

```python
def test_capabilities_use_active_stocks_as_denominator(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    seed_stock_basics(db)
    db.upsert(
        "stock_basic",
        [
            {
                "code": "000003.SZ",
                "name": "PT金田A",
                "exchange": "SZ",
                "list_date": date(1991, 7, 3),
                "source": "test",
                "is_st": False,
                "suspended": True,
                "updated_at": datetime(2026, 5, 24, 9, 0),
            }
        ],
        ["code"],
    )

    capabilities = {row["capability"]: row for row in DataService(db).capabilities()}

    assert capabilities["股票基础信息"]["coverage_count"] == 4
    assert capabilities["股票基础信息"]["missing_count"] == 0
    assert capabilities["当天行情快照"]["missing_count"] == 3


def test_capabilities_ignore_inactive_old_data_in_stock_coverage(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    seed_stock_basics(db)
    db.upsert(
        "stock_basic",
        [
            {
                "code": "000003.SZ",
                "name": "PT金田A",
                "exchange": "SZ",
                "list_date": date(1991, 7, 3),
                "source": "test",
                "is_st": False,
                "suspended": True,
                "updated_at": datetime(2026, 5, 24, 9, 0),
            }
        ],
        ["code"],
    )
    db.upsert(
        "historical_bars",
        [
            {
                "code": "000003.SZ",
                "date": date(2026, 5, 24),
                "open": 1.0,
                "high": 1.1,
                "low": 0.9,
                "close": 1.0,
                "prev_close": 1.0,
                "volume": 100,
                "amount": 1000,
                "turn": 1.0,
                "pct_chg": 0.0,
                "tradestatus": "1",
                "is_st": False,
                "source": "test",
                "updated_at": datetime(2026, 5, 24, 15, 0),
            }
        ],
        ["code", "date"],
    )

    capabilities = {row["capability"]: row for row in DataService(db).capabilities()}

    assert capabilities["历史 K 线"]["coverage_count"] == 0
    assert capabilities["历史 K 线"]["missing_count"] == 4
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_data_warehouse.py::test_capabilities_use_active_stocks_as_denominator backend/tests/test_data_warehouse.py::test_capabilities_ignore_inactive_old_data_in_stock_coverage -q
```

Expected: FAIL because capabilities still use all `stock_basic` rows and include inactive old data.

- [ ] **Step 3: Update `refresh_capabilities()` counts**

In `DataService.refresh_capabilities()`, replace:

```python
        total_stocks = self.db.scalar("SELECT COUNT(*) FROM stock_basic") or 0
```

with:

```python
        total_stocks = self.db.scalar("SELECT COUNT(*) FROM stock_basic") or 0
        active_stocks = self.active_stock_count()
```

For stock-based counts, use joins to `stock_basic b` with `ACTIVE_STOCK_FILTER`. Examples:

```python
"历史 K 线": self.db.scalar(
    f"""
    SELECT COUNT(DISTINCT h.code)
    FROM historical_bars h
    JOIN stock_basic b ON b.code = h.code
    WHERE {ACTIVE_STOCK_FILTER}
    """
) or 0,
"股票基础信息": active_stocks,
"换手率": self.db.scalar(
    f"""
    SELECT COUNT(DISTINCT h.code)
    FROM historical_bars h
    JOIN stock_basic b ON b.code = h.code
    WHERE h.turn IS NOT NULL AND {ACTIVE_STOCK_FILTER}
    """
) or 0,
```

Apply the same active join pattern to:

- `当天行情快照`
- `流通市值`
- `RPS`
- `振幅`
- `ST / 停牌状态`
- `每日指标`
- `技术因子`
- `资金流向`
- `筹码分布`
- `概念/行业成分`

When building rows, change denominator logic to:

```python
denominator = coverage if coverage_kind in {"event", "dataset"} else active_stocks if active_stocks else coverage
```

- [ ] **Step 4: Run capability tests to verify GREEN**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_data_warehouse.py::test_capabilities_use_active_stocks_as_denominator backend/tests/test_data_warehouse.py::test_capabilities_ignore_inactive_old_data_in_stock_coverage -q
```

Expected: PASS.

## Task 3: Warehouse Status Filter

**Files:**
- Modify: `backend/app/services/data_service.py`
- Modify: `backend/app/api/routes.py`
- Test: `backend/tests/test_data_warehouse.py`

- [ ] **Step 1: Write failing warehouse status tests**

Append this test to `backend/tests/test_data_warehouse.py`:

```python
def test_stock_warehouse_filters_inactive_status_and_falls_back_for_exact_code_search(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    seed_stock_basics(db)
    db.upsert(
        "stock_basic",
        [
            {
                "code": "000003.SZ",
                "name": "PT金田A",
                "exchange": "SZ",
                "list_date": date(1991, 7, 3),
                "source": "test",
                "is_st": False,
                "suspended": True,
                "updated_at": datetime(2026, 5, 24, 9, 0),
            }
        ],
        ["code"],
    )

    service = DataService(db)
    active = service.list_stocks()
    inactive = service.list_stocks(status="inactive")
    all_rows = service.list_stocks(status="all")
    exact_search = service.list_stocks(search="000003.SZ")

    assert active["total"] == 4
    assert [row["code"] for row in inactive["rows"]] == ["000003.SZ"]
    assert inactive["rows"][0]["is_active"] is False
    assert inactive["rows"][0]["status_label"] == "非活跃"
    assert all_rows["total"] == 5
    assert exact_search["total"] == 1
    assert exact_search["rows"][0]["code"] == "000003.SZ"
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_data_warehouse.py::test_stock_warehouse_filters_inactive_status_and_falls_back_for_exact_code_search -q
```

Expected: FAIL because `list_stocks()` does not accept `status`.

- [ ] **Step 3: Implement status filtering**

Change `DataService.list_stocks()` signature:

```python
    def list_stocks(
        self,
        limit: int = 50,
        offset: int = 0,
        search: str = "",
        exchange: str = "",
        board: str = "",
        status: str = "active",
    ) -> Dict[str, Any]:
```

Add status filtering after board filtering:

```python
        status = status.lower().strip()
        if status not in {"active", "inactive", "all"}:
            status = "active"
        exact_code_search = bool(re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", text.upper())) if search else False
        if status == "inactive":
            clauses.append("b.suspended IS TRUE")
        elif status == "active" and not exact_code_search:
            clauses.append("b.suspended IS DISTINCT FROM TRUE")
```

Import `re` at the top of `data_service.py`.

Add fields to the SELECT list in `list_stocks()`:

```sql
                   b.suspended IS DISTINCT FROM TRUE AS is_active,
                   CASE WHEN b.suspended IS TRUE THEN '非活跃' ELSE '活跃' END AS status_label,
```

Change `backend/app/api/routes.py` `/data/stocks` endpoint to accept and pass `status`:

```python
    status: str = "active",
) -> Dict[str, Any]:
    return data_service.list_stocks(limit=limit, offset=offset, search=search, exchange=exchange, board=board, status=status)
```

- [ ] **Step 4: Run warehouse status test to verify GREEN**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_data_warehouse.py::test_stock_warehouse_filters_inactive_status_and_falls_back_for_exact_code_search -q
```

Expected: PASS.

## Task 4: Frontend Types and API

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Update overview type**

In `frontend/src/types.ts`, extend `Overview`:

```ts
export interface Overview {
  stock_count: number;
  active_stock_count?: number;
  inactive_stock_count?: number;
  history_rows: number;
  snapshot_rows: number;
  latest_history_date: string | null;
  latest_snapshot_date: string | null;
  turnover_coverage: { count: number; total: number; percent: number };
  latest_analysis: AnalysisRun | null;
  latest_update: TaskRun | null;
  latest_brief: DailyBrief | null;
  warnings: Array<Record<string, unknown>>;
}
```

- [ ] **Step 2: Confirm API filter passthrough**

`frontend/src/api.ts` already passes arbitrary string filters through `api.stocks()`. No code change is needed unless TypeScript complains.

- [ ] **Step 3: Run TypeScript build after UI changes**

Defer build until Task 5 because App changes are required.

## Task 5: Frontend Inactive UI

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Add overview active count copy**

In `Overview`, derive active/inactive counts:

```ts
  const activeStockCount = overview.active_stock_count ?? overview.stock_count;
  const inactiveStockCount = overview.inactive_stock_count ?? Math.max(0, overview.stock_count - activeStockCount);
```

Update the stock metric card:

```tsx
<MetricCard
  label="股票池"
  value={formatInt(activeStockCount)}
  sub={inactiveStockCount > 0 ? `忽略 ${formatInt(inactiveStockCount)} 只非活跃` : '活跃 A 股'}
  icon={<Database size={18} />}
/>
```

- [ ] **Step 2: Pass overview counts into DataMap**

In the `tab === 'map'` branch, pass:

```tsx
          overview={bootstrap.overview}
```

Change `DataMap` props:

```ts
  overview: Overview;
  capabilities: Capability[];
```

Inside `DataMap`, derive:

```ts
  const activeStockCount = overview.active_stock_count ?? overview.stock_count;
  const inactiveStockCount = overview.inactive_stock_count ?? Math.max(0, overview.stock_count - activeStockCount);
```

Render under the data-ledger heading:

```tsx
            <p>按数据类检查本地仓库的新鲜度和字段覆盖。</p>
            <div className="ledger-universe-note">
              按活跃股票统计
              {inactiveStockCount > 0 && <span>已忽略 {formatInt(inactiveStockCount)} 只非活跃股票</span>}
            </div>
```

- [ ] **Step 3: Add warehouse status filter state**

In `Warehouse`, add:

```ts
  const [stockStatus, setStockStatus] = useState<'active' | 'inactive' | 'all'>('active');
```

Add options:

```ts
  const statusOptions = [
    { label: '活跃', value: 'active' },
    { label: '非活跃', value: 'inactive' },
    { label: '全部', value: 'all' },
  ] as const;
```

Pass status to API:

```ts
const data = (await api.stocks(limit, offset, search, { exchange, board, status: stockStatus })) as { rows: Array<Record<string, unknown>>; total: number };
```

Add `stockStatus` to the `useEffect` dependency list.

- [ ] **Step 4: Render warehouse status filter**

Add a filter group after board filters:

```tsx
          <div className="filter-group">
            {statusOptions.map((option) => (
              <button
                key={option.value}
                className={stockStatus === option.value ? 'filter-chip active' : 'filter-chip'}
                onClick={() => { setOffset(0); setStockStatus(option.value); }}
              >
                {option.label}
              </button>
            ))}
          </div>
```

- [ ] **Step 5: Render inactive badge in stock cell**

Inside the stock name `<strong>`, use:

```tsx
<strong>
  {String(row.name || '')}
  {row.status_label === '非活跃' && <span className="stock-status-badge inactive">非活跃</span>}
</strong>
```

- [ ] **Step 6: Add CSS**

In `frontend/src/styles.css`, add:

```css
.ledger-universe-note {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  color: var(--muted);
  font-size: 12px;
}

.ledger-universe-note span {
  color: var(--warning);
}

.stock-status-badge {
  display: inline-flex;
  align-items: center;
  margin-left: 8px;
  padding: 2px 6px;
  border: 1px solid rgba(225, 181, 87, 0.35);
  background: rgba(225, 181, 87, 0.08);
  color: #d7b46a;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
}
```

- [ ] **Step 7: Run frontend build**

Run:

```bash
npm --prefix frontend run build
```

Expected: PASS.

## Task 6: Full Verification

**Files:**
- All changed files.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_data_warehouse.py backend/tests/test_tushare_enrichment_update.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full backend tests**

Run:

```bash
PYTHONPATH=. pytest backend/tests -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
npm --prefix frontend run build
```

Expected: PASS.

- [ ] **Step 4: Inspect git diff**

Run:

```bash
git diff --stat
git diff --check
```

Expected: relevant files only; `git diff --check` exits 0.

- [ ] **Step 5: Commit implementation**

Run:

```bash
git add backend/app/services/data_service.py backend/app/api/routes.py backend/tests/test_data_warehouse.py frontend/src/App.tsx frontend/src/api.ts frontend/src/types.ts frontend/src/styles.css
git commit -m "Add inactive stock coverage labels"
```

Expected: commit succeeds on `main`.
