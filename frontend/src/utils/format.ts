export function formatPercent(value: unknown, digits = 2): string {
  const numeric = toNumber(value);
  if (numeric === null) return '暂无数据';
  return `${numeric.toFixed(digits)}%`;
}

export function formatReturnPercent(value: unknown, digits = 2, fallback = '待复盘'): string {
  const numeric = toNumber(value);
  if (numeric === null) return fallback;
  return `${(numeric * 100).toFixed(digits)}%`;
}

export function formatRatio(value: unknown, digits = 2): string {
  const numeric = toNumber(value);
  if (numeric === null) return '暂无数据';
  return numeric.toFixed(digits);
}

export function formatMoney(value: unknown): string {
  const numeric = toNumber(value);
  if (numeric === null) return '暂无数据';
  const abs = Math.abs(numeric);
  if (abs >= 100_000_000) return `${(numeric / 100_000_000).toFixed(2)}亿`;
  if (abs >= 10_000) return `${(numeric / 10_000).toFixed(1)}万`;
  return numeric.toFixed(0);
}

export function formatNumber(value: unknown, digits = 0): string {
  const numeric = toNumber(value);
  if (numeric === null) return '暂无数据';
  return numeric.toLocaleString('zh-CN', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

export function shortText(value: unknown, fallback = '暂无'): string {
  const text = typeof value === 'string' ? value.trim() : '';
  return text || fallback;
}

export function toNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return numeric;
  }
  return null;
}
