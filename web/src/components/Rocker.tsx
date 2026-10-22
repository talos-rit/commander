import { useId, type ReactNode } from "react";

export interface RockerOption<T extends string> {
  value: T;
  label: ReactNode;
  /** Shown on hover, and under the switch when `describe` is set. */
  description?: string;
}

interface Props<T extends string> {
  label: string;
  value: T;
  options: readonly [RockerOption<T>, RockerOption<T>];
  onChange: (value: T) => void;
  disabled?: boolean;
  /** Tooltip explaining why the switch is disabled. */
  disabledReason?: string;
  describe?: boolean;
  size?: "sm" | "md";
}

/** A two-way switch with an option label on each side of the track. */
export function Rocker<T extends string>({
  label,
  value,
  options,
  onChange,
  disabled = false,
  disabledReason,
  describe = false,
  size = "md",
}: Props<T>) {
  const reasonId = useId();
  const [left, right] = options;
  const current = value === right.value ? right : left;
  const other = current === left ? right : left;
  const select = (option: RockerOption<T>) => {
    if (!disabled && option.value !== value) onChange(option.value);
  };

  const side = (option: RockerOption<T>, position: "left" | "right") => (
    <button
      type="button"
      role="radio"
      aria-checked={option.value === value}
      className={`rocker__side rocker__side--${position}`}
      title={option.description}
      disabled={disabled}
      onClick={() => select(option)}
    >
      {option.label}
    </button>
  );

  const showReason = disabled && Boolean(disabledReason);

  return (
    <div className={`rocker-field ${disabled ? "is-disabled" : ""}`} data-tooltip={showReason ? disabledReason : undefined}>
      <div
        className={`rocker rocker--${size}`}
        role="radiogroup"
        aria-label={label}
        aria-describedby={showReason ? reasonId : undefined}
        data-side={current === left ? "left" : "right"}
      >
        {side(left, "left")}
        <button
          type="button"
          className="rocker__track"
          tabIndex={-1}
          aria-hidden="true"
          disabled={disabled}
          onClick={() => select(other)}
        >
          <span className="rocker__thumb" />
        </button>
        {side(right, "right")}
      </div>
      {showReason && (
        <span id={reasonId} className="visually-hidden">
          {disabledReason}
        </span>
      )}
      {describe && current.description && <p className="rocker__desc">{current.description}</p>}
    </div>
  );
}
