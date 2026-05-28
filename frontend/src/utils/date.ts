export function formatDate(value: unknown): string {
  if (!value) return '--';
  const raw = String(value);
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return raw.slice(0, 19);
  return parsed.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' });
}

export function formatDateTime(value: unknown): string {
  if (!value) return '--';
  const parsed = new Date(String(value));
  if (Number.isNaN(parsed.getTime())) return String(value).slice(0, 19);
  return parsed.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}
