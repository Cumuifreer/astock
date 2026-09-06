import assert from 'node:assert/strict';
import { test, afterEach, after } from 'node:test';
import { mkdtempSync, mkdirSync, rmSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { JSDOM } from 'jsdom';
import { build } from 'esbuild';

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost/' });
for (const name of ['window', 'document', 'HTMLElement', 'Element', 'Node', 'DocumentFragment', 'MutationObserver', 'Event', 'CustomEvent', 'HTMLInputElement', 'HTMLSelectElement', 'localStorage']) {
  globalThis[name] = dom.window[name];
}
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });
globalThis.getComputedStyle = dom.window.getComputedStyle;
globalThis.requestAnimationFrame = callback => setTimeout(callback, 0);
globalThis.cancelAnimationFrame = clearTimeout;
globalThis.ResizeObserver = class {
  static observed = new WeakSet();
  constructor(callback) { this.callback = callback; }
  observe(target) {
    if (globalThis.ResizeObserver.observed.has(target)) return;
    globalThis.ResizeObserver.observed.add(target);
    this.callback([{ target, contentRect: { width: 1024, height: 600 } }]);
  }
  unobserve() {}
  disconnect() {}
};
Element.prototype.scrollIntoView = () => {};
Element.prototype.hasPointerCapture = () => false;
Element.prototype.setPointerCapture = () => {};
Element.prototype.releasePointerCapture = () => {};
Element.prototype.getBoundingClientRect = () => ({ top: 0, left: 0, right: 1024, bottom: 600, width: 1024, height: 600, x: 0, y: 0, toJSON() {} });
Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 600 });
Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, value: 600 });
Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, value: 1024 });

const React = await import('react');
const { render, screen, cleanup, fireEvent, waitFor, renderHook } = await import('@testing-library/react');
const { QueryClient, QueryClientProvider } = await import('@tanstack/react-query');
const userEvent = (await import('@testing-library/user-event')).default;
const cache = resolve('node_modules/.cache');
mkdirSync(cache, { recursive: true });
const directory = mkdtempSync(join(cache, 'astock-ui-'));
const outfile = join(directory, 'components.mjs');
await build({
  stdin: { contents: `export { IndicatorMatrix } from './src/pages/scanner/IndicatorMatrix';
    export { CandidateEvidencePanel } from './src/pages/results/CandidateEvidencePanel';
    export { ResultsPage } from './src/pages/results/ResultsPage';
    export { useTaskTerminalInvalidation } from './src/hooks/useTaskTerminalInvalidation';`, resolveDir: process.cwd(), loader: 'tsx' },
  outfile, bundle: true, platform: 'node', format: 'esm', packages: 'external', jsx: 'automatic',
});
const { IndicatorMatrix, CandidateEvidencePanel, ResultsPage, useTaskTerminalInvalidation } = await import(pathToFileURL(outfile).href);
const clients = [];
const originalFetch = globalThis.fetch;
afterEach(() => { cleanup(); for (const client of clients.splice(0)) client.clear(); localStorage.clear(); globalThis.fetch = originalFetch; });
after(() => { dom.window.close(); rmSync(directory, { recursive: true, force: true }); });
const element = React.createElement;
function provider() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, gcTime: 0 } } });
  clients.push(client);
  return { client, wrapper: ({ children }) => element(QueryClientProvider, { client }, children) };
}
const indicators = [
  { id: 'rps20', name: 'RPS20', group: 'technical', group_label: '相对强弱', kind: 'data', status: 'active', data_status: 'executable', supported_actions: ['filter'], supported_operators: ['gte'], description: '20 日相对强弱', default_value: 80, default_operator: 'gte' },
  { id: 'paid', name: '付费筹码', group: 'chip', group_label: '筹码成本', status: 'active', data_status: 'unavailable' },
];
const noop = () => {};


test('indicator search opens matching cards and cannot enable unavailable data', async () => {
  let added;
  render(element(IndicatorMatrix, { indicators, rules: [], config: {}, onAddRule: indicator => { added = indicator; }, onPatchRule: noop, onPatchConfig: noop }));
  assert.equal(screen.queryByRole('switch'), null);
  fireEvent.change(screen.getByRole('textbox', { name: '搜索指标' }), { target: { value: 'RPS' } });
  assert.equal(screen.getAllByRole('button', { name: '关' }).length, 1);
  fireEvent.click(screen.getByRole('button', { name: '关' }));
  assert.equal(added.id, 'rps20');
  assert.equal(screen.queryByText('付费筹码'), null);
});

test('favorite indicators persist and remain available after remount', () => {
  const props = { indicators, rules: [], config: {}, onAddRule: noop, onPatchRule: noop, onPatchConfig: noop };
  const view = render(element(IndicatorMatrix, props));
  fireEvent.change(screen.getByRole('textbox', { name: '搜索指标' }), { target: { value: 'RPS' } });
  fireEvent.click(screen.getByRole('button', { name: '设为常用 RPS20' }));
  assert.deepEqual(JSON.parse(localStorage.getItem('astock.indicator-favorites')), ['rps20']);
  view.unmount();
  render(element(IndicatorMatrix, props));
  fireEvent.change(screen.getByRole('textbox', { name: '搜索指标' }), { target: { value: 'RPS' } });
  assert.equal(screen.getByRole('button', { name: '取消常用 RPS20' }).getAttribute('aria-pressed'), 'true');
});

test('candidate evidence displays rule facts without network requests', () => {
  globalThis.fetch = () => { throw new Error('Evidence must use the saved report'); };
  render(element(CandidateEvidencePanel, { candidate: { code: '000001.SZ', name: '测试', signal_score: 88, reasons: ['成交额达到条件'], metrics: { strategy_rule_results: [{ indicator_name: '换手率', action: 'risk', matched: true, value: 20, reason: '超过设置的上限' }] } } }));
  assert.ok(screen.getByText('成交额达到条件'));
  assert.ok(screen.getByText('换手率：超过设置的上限'));
  assert.equal(screen.queryByText(/AI/), null);
});

test('completed task invalidates its results once without reloading strategy metadata', async () => {
  const { client, wrapper } = provider();
  const keys = [];
  client.invalidateQueries = async options => { keys.push(options.queryKey); };
  const { rerender } = renderHook(({ rows }) => useTaskTerminalInvalidation(rows, true), { wrapper, initialProps: { rows: [] } });
  const rows = [{ id: 'analyze-1', kind: 'analyze', status: 'completed_full' }];
  rerender({ rows });
  await waitFor(() => assert.deepEqual(keys, [['review-overview'], ['result-reports']]));
  rerender({ rows: [...rows] });
  assert.equal(keys.length, 2);
});

test('results display the report market date without bootstrap or AI requests', async () => {
  const { wrapper } = provider();
  const requests = [];
  const analysis = { id: 'run-1', started_at: '2026-09-05T08:00:00', config: { name: '测试策略' }, summary: { strategy_name: '测试策略', trade_date: '2026-09-04', candidate_count: 2 } };
  globalThis.fetch = async (url, options = {}) => {
    requests.push({ url, options });
    const data = url === '/api/analysis/reports' ? { groups: [{ reports: [analysis] }] }
      : url.startsWith('/api/analysis/reports/run-1') ? { analysis, candidates: { rows: [], funnel: [] } }
      : url === '/api/review/overview' ? { trade_date: '2026-09-04', covered_count: 2, stock_count: 2, source: 'Baostock' }
      : url === '/api/watchlist/codes' ? { codes: [] } : {};
    return new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });
  };
  render(element(ResultsPage), { wrapper });
  await waitFor(() => assert.ok(screen.getAllByText('2026-09-04').length >= 1));
  assert.ok(requests.every(request => !request.url.includes('bootstrap') && !request.url.includes('ai-summary')));
});
