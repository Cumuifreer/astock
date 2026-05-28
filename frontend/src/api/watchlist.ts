import type { WatchlistResult } from '../types';
import { patch, post, request } from './client';

export function getWatchlist(): Promise<WatchlistResult> {
  return request<WatchlistResult>('/api/watchlist');
}

export function addWatchlistItems(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return post('/api/watchlist/items', payload);
}

export function updateWatchlistItem(batchId: string, code: string, payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return patch(`/api/watchlist/batches/${encodeURIComponent(batchId)}/items/${encodeURIComponent(code)}`, payload);
}

export function updateWatchlistBatch(batchId: string, payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return patch(`/api/watchlist/batches/${encodeURIComponent(batchId)}`, payload);
}
