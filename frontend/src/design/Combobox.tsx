import { Search } from 'lucide-react';

type ComboboxProps = {
  value: string;
  placeholder?: string;
  onChange: (value: string) => void;
};

export function Combobox({ value, placeholder = '搜索指标或代码', onChange }: ComboboxProps) {
  return (
    <label className="field" style={{ position: 'relative' }}>
      <span>{placeholder}</span>
      <Search size={15} style={{ position: 'absolute', left: 10, bottom: 10, color: 'var(--text-muted)' }} />
      <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} style={{ paddingLeft: 32 }} />
    </label>
  );
}
