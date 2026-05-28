import clsx from 'clsx';

type SwitchProps = {
  checked: boolean;
  label?: string;
  disabled?: boolean;
  onCheckedChange: (checked: boolean) => void;
};

export function Switch({ checked, label, disabled, onCheckedChange }: SwitchProps) {
  return (
    <button
      aria-pressed={checked}
      className={clsx('switch-control', checked && 'checked')}
      data-state={checked ? 'checked' : 'unchecked'}
      disabled={disabled}
      type="button"
      onClick={() => onCheckedChange(!checked)}
    >
      <span className="switch-track" aria-hidden="true">
        <span className="switch-thumb" />
      </span>
      {label ? <span className="switch-label">{label}</span> : null}
    </button>
  );
}
