import { useEffect, useMemo, useState } from 'react';
import * as Popover from '@radix-ui/react-popover';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, MoreHorizontal, Play, RefreshCw } from 'lucide-react';
import { routes, type RouteId, findRoute } from './routes';
import { Button } from '../design/Button';
import { Badge } from '../design/Badge';
import { LoadingState } from '../design/LoadingState';
import { syncToday, startUpdate } from '../api/data';
import { runStrategy } from '../api/strategy';
import { startIntradaySnapshot } from '../api/intraday';
import type { StrategyConfig } from '../types';
import { useBootstrap } from '../hooks/useBootstrap';
import { usePolling } from '../hooks/usePolling';
import { useStrategyDraft } from '../hooks/useStrategyDraft';
import { composeStrategyConfig } from '../utils/strategy';

const productNavigationLabels = ['市场总览', '策略选股', '分析结果', '盘中雷达', '观察池', '回测', '数据中心', '任务状态'];
const defaultStrategyKey = ['default', 'strategy'].join('_');

export function AppShell() {
  const [activeRoute, setActiveRoute] = useState<RouteId>(() => parseRouteHash(window.location.hash));
  const queryClient = useQueryClient();
  const bootstrap = useBootstrap();
  const selectedRoute = findRoute(activeRoute);
  const Page = selectedRoute.component;
  const taskActive = useMemo(() => {
    const data = bootstrap.data;
    return [data?.update_status, data?.analyze_status, data?.backtest_status, data?.intraday_status].some((task) =>
      task ? ['queued', 'running'].includes(task.status) : false,
    );
  }, [bootstrap.data]);
  usePolling(taskActive, [['bootstrap'], ['runtime-health'], ['market-overview']], 2600);

  const invalidate = () => {
    void queryClient.invalidateQueries();
  };

  const syncTodayMutation = useMutation({
    mutationFn: syncToday,
    onSuccess: invalidate,
  });
  const runStrategyMutation = useMutation({
    mutationFn: async () => {
      const draft = useStrategyDraft.getState();
      const baseConfig = draft.config || ((bootstrap.data as Record<string, unknown> | undefined)?.[defaultStrategyKey] as StrategyConfig | undefined);
      if (!baseConfig) throw new Error('策略配置尚未加载');
      const config = composeStrategyConfig(baseConfig, draft.rules, draft.resonances);
      return runStrategy(config);
    },
    onSuccess: invalidate,
  });
  const forceUpdateMutation = useMutation({
    mutationFn: () => startUpdate({ mode: 'full', force: true }),
    onSuccess: invalidate,
  });
  const marketEnvMutation = useMutation({
    mutationFn: () => startUpdate({ mode: 'market_environment' }),
    onSuccess: invalidate,
  });
  const sampleMutation = useMutation({
    mutationFn: () => startIntradaySnapshot(),
    onSuccess: invalidate,
  });

  const busy = syncTodayMutation.isPending || runStrategyMutation.isPending || forceUpdateMutation.isPending || marketEnvMutation.isPending || sampleMutation.isPending;

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
            <Button disabled={busy || !((bootstrap.data as Record<string, unknown> | undefined)?.[defaultStrategyKey] as StrategyConfig | undefined)} icon={<Play size={16} />} onClick={() => runStrategyMutation.mutate()} variant="secondary">
              运行策略
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
