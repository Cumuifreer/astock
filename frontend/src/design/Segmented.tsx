type SegmentedOption<T extends string> = {
  value: T;
  label: string;
};

type SegmentedProps<T extends string> = {
  value: T;
  options: Array<SegmentedOption<T>>;
  onChange: (value: T) => void;
};

export function Segmented<T extends string>({ value, options, onChange }: SegmentedProps<T>) {
  return (
    <div className="segmented">
      {options.map((option) => (
        <button key={option.value} className={option.value === value ? 'active' : undefined} type="button" onClick={() => onChange(option.value)}>
          {option.label}
        </button>
      ))}
    </div>
  );
}
