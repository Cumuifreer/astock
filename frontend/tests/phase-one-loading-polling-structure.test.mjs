import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import test from 'node:test';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '../src');

function read(path) {
  return readFileSync(resolve(root, path), 'utf8');
}

test('app shell renders the route without waiting for bootstrap', () => {
  const shell = read('app/AppShell.tsx');

  assert.doesNotMatch(shell, /bootstrap\.isLoading\s*\?\s*<LoadingState label="启动工作台" \/>/);
  assert.doesNotMatch(shell, /import \{ LoadingState \} from '\.\.\/design\/LoadingState'/);
  assert.match(shell, /<div className="page-content">\s*<Page \/>/);
});

test('terminal task invalidation primes the first fetched recent rows', () => {
  const hook = read('hooks/useTaskTerminalInvalidation.ts');

  assert.match(hook, /primedRecentTaskIds/);
  assert.match(hook, /if \(!recentRowsReady\) return/);
  assert.match(hook, /if \(!primedRecentTaskIds\.current\)/);
  assert.match(hook, /seenTerminalTaskIds\.current\.add\(task\.id\)/);
});

test('status and shell task polling keeps a standby recent-task heartbeat', () => {
  const shell = read('app/AppShell.tsx');
  const status = read('pages/status/StatusPage.tsx');

  assert.match(`${shell}\n${status}`, /standbyRefreshInterval\s*=\s*60_000/);
  assert.match(shell, /hasActiveRows\(normalizeRows<TaskRun>\(query\.state\.data/);
  assert.match(shell, /\?\s*activeRefreshInterval\s*:\s*standbyRefreshInterval/);
  assert.match(shell, /recentTasks = useQuery\([\s\S]*refetchInterval: taskActive \? activeRefreshInterval : standbyRefreshInterval/);
  assert.match(status, /recentTasks = useQuery\([\s\S]*refetchInterval: taskPollingActive \? activeRefreshInterval : standbyRefreshInterval/);
  assert.doesNotMatch(`${shell}\n${status}`, /queryKey: queryKeys\.tasks\.recent\(\)[\s\S]{0,220}refetchInterval:\s*false/);
});

test('status page shows recent terminal tasks in the default view', () => {
  const status = read('pages/status/StatusPage.tsx');
  const maintenanceStart = status.indexOf('{showMaintenance ?');
  const recentStart = status.indexOf('最近任务');

  assert.ok(recentStart > 0, 'StatusPage should render a visible recent task section');
  assert.ok(maintenanceStart < 0 || recentStart < maintenanceStart, 'recent tasks should not be hidden behind maintenance mode');
  assert.match(status, /recentRows\.slice\(0,\s*5\)\.map/);
});

test('status page task cards expose failure reasons', () => {
  const status = read('pages/status/StatusPage.tsx');

  assert.match(status, /taskFailureMessage/);
  assert.match(status, /task\.error_message\s*\|\|\s*task\.warning/);
  assert.match(status, /失败原因/);
});

test('data map only starts the query for the active tab', () => {
  const dataMap = read('pages/data-map/DataMapPage.tsx');

  assert.match(dataMap, /queryKey: \['capabilities'\][\s\S]*enabled: tab === 'health'/);
  assert.match(dataMap, /queryKey: \['source-diagnostics'\][\s\S]*enabled: tab === 'diagnostics'/);
  assert.match(dataMap, /queryKey: \['stocks', query, status, exchange, offset\][\s\S]*enabled: tab === 'warehouse'/);
});

test('overview does not duplicate the default concept heatmap request', () => {
  const overview = read('pages/overview/OverviewPage.tsx');
  const heatmap = read('pages/overview/SectorHeatmap.tsx');

  assert.doesNotMatch(overview, /useBootstrap/);
  assert.match(overview, /latest_brief/);
  assert.match(heatmap, /const shouldFetchHeatmap/);
  assert.match(heatmap, /mode !== 'concept' \|\| !sectors\.length/);
  assert.match(heatmap, /enabled: shouldFetchHeatmap/);
});
