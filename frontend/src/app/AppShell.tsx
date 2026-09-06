import { Suspense, useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { routes, type RouteId, findRoute } from './routes';
import { Button } from '../design/Button';
import { Badge } from '../design/Badge';
import { getTasks } from '../api/data';
import { queryKeys } from '../api/queryKeys';
import { useTaskTerminalInvalidation } from '../hooks/useTaskTerminalInvalidation';
import type { TaskRun } from '../types';
import { normalizeRows } from '../utils/metrics';

const productNavigationLabels = routes.map(route => route.label);
const activeRefreshInterval = 2600;
const standbyRefreshInterval = 60_000;

export function AppShell() {
  const [activeRoute, setActiveRoute] = useState<RouteId>(() => parseRouteHash(window.location.hash));
  const selectedRoute = findRoute(activeRoute);
  const Page = selectedRoute.component;
  const activeTasks = useQuery({
    queryKey: queryKeys.tasks.active(),
    queryFn: () => getTasks({ status: 'queued,running', limit: 50 }),
    refetchInterval: (query) =>
      hasActiveRows(normalizeRows<TaskRun>(query.state.data as { rows?: TaskRun[] } | TaskRun[] | undefined)) ? activeRefreshInterval : standbyRefreshInterval,
  });
  const activeRows = normalizeRows<TaskRun>(activeTasks.data);
  const taskActive = hasActiveRows(activeRows);
  const recentTasks = useQuery({
    queryKey: queryKeys.tasks.recent(),
    queryFn: () => getTasks({ status: 'completed_full,completed_partial,failed', limit: 50 }),
    refetchInterval: taskActive ? activeRefreshInterval : standbyRefreshInterval,
  });
  useTaskTerminalInvalidation(normalizeRows<TaskRun>(recentTasks.data), recentTasks.isFetched);

  useEffect(() => {
    const handleHashChange = () => setActiveRoute(parseRouteHash(window.location.hash));
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const selectRoute = (id: RouteId) => {
    setActiveRoute(id);
    window.history.replaceState(null, '', `#${id}`);
  };

  return (
    <div className="workbench-shell">
      <aside className="workbench-sidebar">
        <div className="brand-lockup">
          <div className="brand-mark">A</div>
          <div>
            <h1 className="brand-title">astock</h1>
            <p className="brand-subtitle">收盘选股与复盘</p>
          </div>
        </div>
        <nav className="nav-stack" aria-label={productNavigationLabels.join(' / ')}>
          {routes.map((route) => (
            <NavButton active={route.id === activeRoute} key={route.id} routeId={route.id} onClick={selectRoute} />
          ))}
        </nav>
      </aside>

      <main className="workbench-main">
        <nav className="mobile-nav" aria-label="移动导航">
          {routes.map((route) => (
            <NavButton active={route.id === activeRoute} key={route.id} routeId={route.id} onClick={selectRoute} />
          ))}
        </nav>
        <header className="topbar">
          <div className="topbar-title">
            <Badge tone="info">{selectedRoute.eyebrow}</Badge>
            <h1>{selectedRoute.label}</h1>
            <p>{selectedRoute.description}</p>
          </div>
          <div className="topbar-actions">
            <Button variant="secondary" onClick={() => selectRoute('data-map')}>
              {taskActive ? `任务运行中 · ${activeRows.length}` : '更新数据'}
            </Button>
          </div>
        </header>
        <div className="page-content">
          <Suspense fallback={<p role="status">正在加载…</p>}><Page /></Suspense>
        </div>
      </main>
    </div>
  );
}

function hasActiveRows(rows: TaskRun[]) {
  return rows.some((task) => ['queued', 'running'].includes(task.status));
}

function parseRouteHash(hash: string): RouteId {
  const raw = hash.replace(/^#\/?/, '').split('?')[0];
  const value = (raw === 'status' ? 'data-map' : raw) as RouteId;
  return routes.some((route) => route.id === value) ? value : 'results';
}

function NavButton({ routeId, active, onClick }: { routeId: RouteId; active: boolean; onClick: (id: RouteId) => void }) {
  const route = findRoute(routeId);
  const Icon = route.icon;
  return (
    <button className={active ? 'nav-button active' : 'nav-button'} type="button" onClick={() => onClick(routeId)}>
      <Icon size={17} />
      <span>{route.label}</span>
    </button>
  );
}
