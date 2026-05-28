import { Check } from 'lucide-react';
import clsx from 'clsx';

type CheckTileProps = {
  checked: boolean;
  label: string;
  onCheckedChange: (checked: boolean) => void;
  id?: string;
  disabled?: boolean;
};

export function CheckTile({ checked, label, onCheckedChange, id, disabled }: CheckTileProps) {
  return (
    <button
      aria-pressed={checked}
      className={clsx('check-tile', checked && 'checked')}
      disabled={disabled}
      id={id}
      type="button"
      onClick={() => onCheckedChange(!checked)}
    >
      <span className="check-box" aria-hidden="true">{checked ? <Check size={13} strokeWidth={3} /> : null}</span>
      <span>{label}</span>
    </button>
  );
}
