import type { ComponentType } from 'react';
import { Activity, BarChart3, Database, FlaskConical, Gauge, Radar, Star, Workflow } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { OverviewPage } from '../pages/overview/OverviewPage';
import { StrategyPage } from '../pages/scanner/StrategyPage';
import { ResultsPage } from '../pages/results/ResultsPage';
import { IntradayPage } from '../pages/intraday/IntradayPage';
import { WatchlistPage } from '../pages/watchlist/WatchlistPage';
import { BacktestPage } from '../pages/backtest/BacktestPage';
import { DataMapPage } from '../pages/data-map/DataMapPage';
import { StatusPage } from '../pages/status/StatusPage';

export type RouteId = 'overview' | 'scanner' | 'results' | 'intraday' | 'watchlist' | 'backtest' | 'data-map' | 'status';

export type RouteDefinition = {
  id: RouteId;
  label: string;
  eyebrow: string;
  description: string;
  icon: LucideIcon;
  component: ComponentType;
};

export const routes: RouteDefinition[] = [
  {
    id: 'overview',
    label: '市场总览',
    eyebrow: '总览',
    description: '市场状态、仓位建议、主线题材和今日提示。',
    icon: Gauge,
    component: OverviewPage,
  },
  {
    id: 'scanner',
    label: '策略选股',
    eyebrow: '研究',
    description: '配置股票池、筛选条件、评分因子、风险控制和展示字段。',
    icon: Radar,
    component: StrategyPage,
  },
  {
    id: 'results',
    label: '分析结果',
    eyebrow: '结果',
    description: '候选表和结构化证据面板，解释为什么入选与风险在哪。',
    icon: BarChart3,
    component: ResultsPage,
  },
  {
    id: 'intraday',
    label: '盘中雷达',
    eyebrow: '盘中',
    description: '异动、低吸、风险三榜和题材同步脉冲。',
    icon: Activity,
    component: IntradayPage,
  },
  {
    id: 'watchlist',
    label: '观察池',
    eyebrow: '观察',
    description: '按交易假设跟踪候选的后验表现、触发规则和失效条件。',
    icon: Star,
    component: WatchlistPage,
  },
  {
    id: 'backtest',
    label: '回测',
    eyebrow: '回测',
    description: '拆分信号评估和组合回测，检查规则预测力和组合表现。',
    icon: FlaskConical,
    component: BacktestPage,
  },
  {
    id: 'data-map',
    label: '数据中心',
    eyebrow: '数据',
    description: '数据新鲜度、覆盖率、用途和补齐入口。',
    icon: Database,
    component: DataMapPage,
  },
  {
    id: 'status',
    label: '任务状态',
    eyebrow: '任务',
    description: '任务队列、当前进度、定时计划和失败诊断。',
    icon: Workflow,
    component: StatusPage,
  },
];

export const defaultRoute = routes[0];

export function findRoute(id: RouteId): RouteDefinition {
  return routes.find((route) => route.id === id) || defaultRoute;
}
