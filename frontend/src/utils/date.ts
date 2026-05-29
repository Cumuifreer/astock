const BEIJING_TIME_ZONE = 'Asia/Shanghai';
const dateOnlyPattern = /^\d{4}-\d{2}-\d{2}$/;
const explicitTimeZonePattern = /(?:Z|[+-]\d{2}:?\d{2})$/i;

type DateTimeSource = 'utc' | 'china-local';

export function formatDate(value: unknown): string {
  if (!value) return '待同步';
  const raw = String(value);
  if (dateOnlyPattern.test(raw)) return raw;
  const parsed = parseDateTime(value, 'utc');
  if (Number.isNaN(parsed.getTime())) return raw.slice(0, 19);
  return formatBeijingDate(parsed);
}

export function formatDateTime(value: unknown, source: DateTimeSource = 'utc'): string {
  if (!value) return '待同步';
  const parsed = parseDateTime(value, source);
  if (Number.isNaN(parsed.getTime())) return String(value).slice(0, 19);
  return formatBeijingDateTime(parsed);
}

export function formatChinaDateTime(value: unknown): string {
  return formatDateTime(value, 'china-local');
}

export function dateTimeToMs(value: unknown, source: DateTimeSource = 'utc'): number {
  if (!value) return Number.NaN;
  return parseDateTime(value, source).getTime();
}

export function todayISO(now: Date = new Date()): string {
  return formatBeijingDate(now);
}

function parseDateTime(value: unknown, source: DateTimeSource): Date {
  if (value instanceof Date) return value;
  const raw = String(value).trim();
  if (!raw) return new Date(Number.NaN);
  if (dateOnlyPattern.test(raw)) {
    return new Date(`${raw}T00:00:00${source === 'china-local' ? '+08:00' : 'Z'}`);
  }
  if (explicitTimeZonePattern.test(raw)) return new Date(raw);
  const normalized = raw.includes('T') ? raw : raw.replace(' ', 'T');
  return new Date(`${normalized}${source === 'china-local' ? '+08:00' : 'Z'}`);
}

function formatBeijingDate(date: Date): string {
  const parts = beijingParts(date, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function formatBeijingDateTime(date: Date): string {
  const parts = beijingParts(date, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  });
  return `${parts.month}/${parts.day} ${parts.hour}:${parts.minute}`;
}

function beijingParts(date: Date, options: Intl.DateTimeFormatOptions): Record<string, string> {
  return Object.fromEntries(
    new Intl.DateTimeFormat('zh-CN', {
      timeZone: BEIJING_TIME_ZONE,
      ...options,
    })
      .formatToParts(date)
      .filter((part) => part.type !== 'literal')
      .map((part) => [part.type, part.value]),
  );
}
