import { lazy, type ComponentType } from 'react';
import { BarChart3, Database, SlidersHorizontal, Star, type LucideIcon } from 'lucide-react';

export type RouteId = 'results' | 'scanner' | 'watchlist' | 'data-map';
export type RouteDefinition = {
  id: RouteId; label: string; eyebrow: string; description: string;
  icon: LucideIcon; component: ComponentType;
};
export const routes: RouteDefinition[] = [
  { id: 'results', label: '收盘复盘', eyebrow: '复盘', description: '查看日线覆盖、筛选结果和入选依据。', icon: BarChart3,
    component: lazy(() => import('../pages/results/ResultsPage').then(m => ({ default: m.ResultsPage }))) },
  { id: 'scanner', label: '策略选股', eyebrow: '策略', description: '自由选择指标、条件和评分，保存自己的选股方法。', icon: SlidersHorizontal,
    component: lazy(() => import('../pages/scanner/StrategyPage').then(m => ({ default: m.StrategyPage }))) },
  { id: 'watchlist', label: '观察池', eyebrow: '观察', description: '记录观察理由和复盘笔记，跟踪后续日线表现。', icon: Star,
    component: lazy(() => import('../pages/watchlist/WatchlistPage').then(m => ({ default: m.WatchlistPage }))) },
  { id: 'data-map', label: '数据与任务', eyebrow: '数据', description: '更新收盘日线，检查数据覆盖和任务进度。', icon: Database,
    component: lazy(() => import('../pages/data-map/DataMapPage').then(m => ({ default: m.DataMapPage }))) },
];
export const defaultRoute = routes[0];
export function findRoute(id: RouteId): RouteDefinition {
  return routes.find(route => route.id === id) || defaultRoute;
}
