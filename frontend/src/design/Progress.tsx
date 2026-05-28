import clsx from 'clsx';

const terminalProgressStates = new Set(['completed_full', 'completed_partial', 'failed', 'skipped']);
const indeterminateProgressStates = new Set(['queued', 'running']);

type ProgressProps = {
  value?: number | null;
  label?: string;
  state?: string | null;
};

export function Progress({ value, label, state }: ProgressProps) {
  const hasValue = typeof value === 'number' && Number.isFinite(value);
  const normalizedState = state || 'running';
  const isTerminal = terminalProgressStates.has(normalizedState);
  const isIndeterminate = !hasValue && indeterminateProgressStates.has(normalizedState);
  const resolvedValue = hasValue ? Math.max(0, Math.min(100, value)) : isTerminal ? 100 : undefined;
  return (
    <div
      aria-label={label || '进度'}
      aria-valuenow={resolvedValue}
      className={clsx('progress-track', normalizedState)}
      role="progressbar"
    >
      <div
        className={clsx('progress-bar', normalizedState, { indeterminate: isIndeterminate })}
        style={resolvedValue !== undefined ? { width: `${resolvedValue}%` } : undefined}
      />
    </div>
  );
}
