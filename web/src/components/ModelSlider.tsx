import { useEffect, useState } from "react";

export const YOLO_SIZES = [
  { value: "yolo_nano", short: "N", name: "Nano" },
  { value: "yolo_small", short: "S", name: "Small" },
  { value: "yolo_medium", short: "M", name: "Medium" },
  { value: "yolo_large", short: "L", name: "Large" },
  { value: "yolo_xlarge", short: "XL", name: "Extra large" },
] as const;

interface Props {
  label: string;
  /** Installed model options; anything that is not a YOLO size is ignored. */
  options: string[];
  /** Selected model; `null` shows `fallback` (the model Auto-Track would load). */
  value: string | null;
  fallback?: string;
  onChange: (model: string) => void;
  disabled?: boolean;
}

/** Discrete slider over the installed YOLO sizes, smallest to largest. */
export function ModelSlider({ label, options, value, fallback = "yolo_nano", onChange, disabled = false }: Props) {
  const sizes = YOLO_SIZES.filter((size) => options.includes(size.value));
  const indexOf = (model: string | null) => sizes.findIndex((size) => size.value === model);
  const selected = indexOf(value) >= 0 ? indexOf(value) : Math.max(0, indexOf(fallback));
  const [position, setPosition] = useState(selected);

  useEffect(() => setPosition(selected), [selected]);

  if (sizes.length === 0) {
    return (
      <p className="hint hint--warn">
        No YOLO model installed. Run <code>uv sync --extra yolo</code> and restart commander-web.
      </p>
    );
  }

  // Loading a model is expensive, so only report the size once the user lets go.
  const commit = (index = position) => {
    if (index !== indexOf(value)) onChange(sizes[index].value);
  };
  const shown = sizes[position] ?? sizes[0];

  return (
    <div className="slider">
      <div className="slider__head">
        <span className="slider__value">
          {shown.name} <code>{shown.value}</code>
        </span>
        <span className="slider__scale">faster ← → more accurate</span>
      </div>
      <input
        type="range"
        className="slider__input"
        aria-label={label}
        aria-valuetext={`${shown.name} (${shown.value})`}
        min={0}
        max={sizes.length - 1}
        step={1}
        value={position}
        disabled={disabled || sizes.length === 1}
        style={{ "--fill": sizes.length > 1 ? `${(position / (sizes.length - 1)) * 100}%` : "0%" } as React.CSSProperties}
        onChange={(event) => setPosition(Number(event.target.value))}
        onPointerUp={() => commit()}
        onKeyUp={() => commit()}
        onBlur={() => commit()}
      />
      <div className="slider__ticks">
        {sizes.map((size, index) => (
          <button
            key={size.value}
            type="button"
            className={`slider__tick ${index === position ? "is-active" : ""}`}
            title={size.name}
            aria-label={`Use ${size.name}`}
            disabled={disabled}
            onClick={() => {
              setPosition(index);
              commit(index);
            }}
          >
            {size.short}
          </button>
        ))}
      </div>
    </div>
  );
}
