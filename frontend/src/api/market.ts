import { request } from './client';

export type MarketState = {
  trade_date?: string;
  label?: string;
  score?: number;
  suggested_position?: string;
  risk_level?: string;
  headline?: string;
  key_risks?: string[];
  key_opportunities?: string[];
};

export type MarketPulse = Record<string, number | string | null | undefined>;

export type SectorHeatNode = {
  code?: string;
  sector_code?: string;
  name?: string;
  sector_name?: string;
  type?: string;
  sector_type?: string;
  pct_chg?: number | null;
  amount?: number | null;
  net_amount?: number | null;
  company_count?: number | null;
  limit_up_count?: number | null;
  strong_count?: number | null;
  leader_code?: string | null;
  leader_name?: string | null;
  heat_score?: number | null;
};

export type DailyActionItem = {
  id: string;
  priority: 'high' | 'medium' | 'low' | string;
  category: string;
  title: string;
  description: string;
  target_type?: string;
  target_code?: string;
  action?: string;
};

export type DataFreshnessItem = {
  label?: string;
  capability?: string;
  latest_update?: string | null;
  status?: string;
  description?: string;
};

export type MarketOverview = {
  trade_date?: string;
  state?: MarketState;
  pulse?: MarketPulse;
  sector_heatmap?: SectorHeatNode[];
  action_items?: DailyActionItem[];
  data_freshness?: DataFreshnessItem[];
  brief?: {
    title?: string;
    bullets?: string[];
  };
};

export function getMarketOverview(): Promise<MarketOverview> {
  return request<MarketOverview>('/api/market/overview');
}

export function getSectorHeatmap(type = 'concept', metric = 'heat', limit = 80): Promise<{ rows?: SectorHeatNode[] } | SectorHeatNode[]> {
  const params = new URLSearchParams({ type, metric, limit: String(limit) });
  return request<{ rows?: SectorHeatNode[] } | SectorHeatNode[]>(`/api/market/sector-heatmap?${params.toString()}`);
}
