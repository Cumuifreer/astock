import { useEffect, useState } from 'react';
import * as Popover from '@radix-ui/react-popover';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, MoreHorizontal, RefreshCw } from 'lucide-react';
import { routes, type RouteId, findRoute } from './routes';
import { Button } from '../design/Button';
import { Badge } from '../design/Badge';
import { LoadingState } from '../design/LoadingState';
import { useToast } from '../design/Toast';
import { syncToday, startUpdate, getTasks } from '../api/data';
import { queryKeys } from '../api/queryKeys';
import { startIntradaySnapshot } from '../api/intraday';
import { useBootstrap } from '../hooks/useBootstrap';
import { useActiveTaskPolling } from '../hooks/useActiveTaskPolling';
import { useTaskTerminalInvalidation } from '../hooks/useTaskTerminalInvalidation';
import type { TaskRun } from '../types';
import { normalizeRows } from '../utils/metrics';

const productNavigationLabels = ['市场总览', '策略选股', '分析结果', '盘中雷达', '观察池', '回测', '数据中心', '任务状态'];

export function AppShell() {
  const [activeRoute, setActiveRoute] = useState<RouteId>(() => parseRouteHash(window.location.hash));
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const bootstrap = useBootstrap();
  const selectedRoute = findRoute(activeRoute);
  const Page = selectedRoute.component;
  const activeTasks = useQuery({
    queryKey: queryKeys.tasks.active(),
    queryFn: () => getTasks({ status: 'queued,running', limit: 50 }),
    refetchInterval: (query) => (hasActiveRows(normalizeRows<TaskRun>(query.state.data as { rows?: TaskRun[] } | TaskRun[] | undefined)) ? 2600 : false),
  });
  const activeRows = normalizeRows<TaskRun>(activeTasks.data);
  const taskActive = useActiveTaskPolling(bootstrap.data, activeRows);
  const recentTasks = useQuery({
    queryKey: queryKeys.tasks.recent(),
    queryFn: () => getTasks({ status: 'completed_full,completed_partial,failed', limit: 50 }),
    refetchInterval: taskActive ? 2600 : false,
  });
  useTaskTerminalInvalidation(normalizeRows<TaskRun>(recentTasks.data));

  const invalidate = () => {
    void queryClient.invalidateQueries();
  };
  const goToStatus = () => {
    setActiveRoute('status');
    window.history.replaceState(null, '', '#status');
  };
  const handleTaskStarted = (message = '任务已开始，可在任务状态查看进度') => {
    invalidate();
    goToStatus();
    showToast(message, 'success');
  };
  const handleTaskError = (error: unknown) => {
    showToast(error instanceof Error ? error.message : '任务启动失败', 'danger');
  };

  const syncTodayMutation = useMutation({
    mutationFn: syncToday,
    onSuccess: () => handleTaskStarted(),
    onError: handleTaskError,
  });
  const forceUpdateMutation = useMutation({
    mutationFn: () => startUpdate({ mode: 'full', force: true }),
    onSuccess: () => handleTaskStarted('强制全量更新已开始，可在任务状态查看进度'),
    onError: handleTaskError,
  });
  const marketEnvMutation = useMutation({
    mutationFn: () => startUpdate({ mode: 'market_environment' }),
    onSuccess: () => handleTaskStarted('市场环境重算已开始，可在任务状态查看进度'),
    onError: handleTaskError,
  });
  const sampleMutation = useMutation({
    mutationFn: () => startIntradaySnapshot(),
    onSuccess: () => handleTaskStarted('盘中采样已开始，可在任务状态查看进度'),
    onError: handleTaskError,
  });

  const busy = syncTodayMutation.isPending || forceUpdateMutation.isPending || marketEnvMutation.isPending || sampleMutation.isPending;

  useEffect(() => {
    const handleHashChange = () => setActiveRoute(parseRouteHash(window.location.hash));
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const selectRoute = (id: RouteId) => {
    setActiveRoute(id);
    window.history.replaceState(null, '', `#${id}`);
  };
  const openDataHealth = () => {
    setActiveRoute('data-map');
    window.history.replaceState(null, '', '#data-map?tab=health');
    window.dispatchEvent(new CustomEvent('data-map-tab', { detail: 'health' }));
  };

  return (
    <div className="workbench-shell">
      <aside className="workbench-sidebar">
        <div className="brand-lockup">
          <div className="brand-mark">A</div>
          <div>
            <h1 className="brand-title">astock</h1>
            <p className="brand-subtitle">A 股量化工作台</p>
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
            <Button disabled={busy} icon={<RefreshCw size={16} />} onClick={() => syncTodayMutation.mutate()} variant="primary">
              同步今日数据
            </Button>
            <Popover.Root>
              <Popover.Trigger asChild>
                <Button aria-label="更多操作" icon={<MoreHorizontal size={16} />} variant="ghost">
                  <ChevronDown size={14} />
                </Button>
              </Popover.Trigger>
              <Popover.Portal>
                <Popover.Content align="end" className="popover-content" sideOffset={8} style={{ padding: 8, width: 220 }}>
                  <div className="list-stack">
                    <Button disabled={busy} onClick={openDataHealth} variant="ghost">
                      打开数据中心
                    </Button>
                    <Button disabled={busy} onClick={() => marketEnvMutation.mutate()} variant="ghost">
                      重算市场环境
                    </Button>
                    <Button disabled={busy} onClick={() => sampleMutation.mutate()} variant="ghost">
                      盘中采样一次
                    </Button>
                    <Button disabled={busy} onClick={() => forceUpdateMutation.mutate()} variant="ghost">
                      强制全量更新
                    </Button>
                  </div>
                </Popover.Content>
              </Popover.Portal>
            </Popover.Root>
          </div>
        </header>
        <div className="page-content">{bootstrap.isLoading ? <LoadingState label="启动工作台" /> : <Page />}</div>
      </main>
    </div>
  );
}

function hasActiveRows(rows: TaskRun[]) {
  return rows.some((task) => ['queued', 'running'].includes(task.status));
}

function parseRouteHash(hash: string): RouteId {
  const value = hash.replace(/^#\/?/, '').split('?')[0] as RouteId;
  return routes.some((route) => route.id === value) ? value : 'overview';
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
