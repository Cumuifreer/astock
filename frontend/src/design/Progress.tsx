type ProgressProps = {
  value?: number | null;
  label?: string;
};

export function Progress({ value, label }: ProgressProps) {
  const hasValue = typeof value === 'number' && Number.isFinite(value);
  return (
    <div aria-label={label || '进度'} className="progress-track" role="progressbar" aria-valuenow={hasValue ? value : undefined}>
      <div className={hasValue ? 'progress-bar' : 'progress-bar indeterminate'} style={hasValue ? { width: `${Math.max(0, Math.min(100, value))}%` } : undefined} />
    </div>
  );
}
