import type { ReactNode } from "react";

export interface SegmentOption<T extends string | number> {
  value: T;
  label: ReactNode;
  title?: string;
  disabled?: boolean;
}

interface Props<T extends string | number> {
  label: string;
  value: T;
  options: SegmentOption<T>[];
  onChange: (value: T) => void;
  size?: "sm" | "md";
}

export function Segmented<T extends string | number>({ label, value, options, onChange, size = "md" }: Props<T>) {
  return (
    <div className={`segmented segmented--${size}`} role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button
          key={String(option.value)}
          type="button"
          role="radio"
          aria-checked={option.value === value}
          className="segmented__option"
          title={option.title}
          disabled={option.disabled}
          onClick={() => option.value !== value && onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
