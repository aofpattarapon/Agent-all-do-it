interface SegOption<T extends string> {
  value: T;
  label: string;
}

interface PixelSegmentedProps<T extends string> {
  options: SegOption<T>[];
  value: T;
  onChange: (value: T) => void;
}

export function PixelSegmented<T extends string>({ options, value, onChange }: PixelSegmentedProps<T>) {
  return (
    <div className="pix-seg">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          className={opt.value === value ? "pix-on" : ""}
          onClick={() => onChange(opt.value)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
