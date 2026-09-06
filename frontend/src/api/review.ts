import { request } from './client';
import type { TaskRun } from '../types';

export type ReviewOverview = {
  trade_date: string | null;
  stock_count: number;
  covered_count: number;
  history_rows: number;
  source: string;
  latest_update: TaskRun | null;
  schedule_enabled: boolean;
  schedule_time: string;
};
export const getReviewOverview = () => request<ReviewOverview>('/api/review/overview');
