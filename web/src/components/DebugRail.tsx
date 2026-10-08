import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Box, Gauge, House, Radio } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Direction, JogMode, Status, Telemetry } from "../types";
import { ModelSlider } from "./ModelSlider";
import { Rocker, type RockerOption } from "./Rocker";

export const JOG_OPTIONS: readonly [RockerOption<JogMode>, RockerOption<JogMode>] = [
  { value: "discrete", label: "Discrete", description: "Sends repeated step commands while held" },
  { value: "continuous", label: "Continuous", description: "Moves smoothly until you release" },
];

type Axis = "x" | "y" | "z";
type JointName = "shoulder" | "elbow";

interface Props {
  status: Status;
  onMoveStart: (direction: Direction) => void;
  onMoveStop: (direction: Direction) => void;
  onCartesianStart: (x: -1 | 0 | 1, y: -1 | 0 | 1, z: -1 | 0 | 1) => void;
  onCartesianStop: () => void;
  onJointStart: (axis: JointName, direction: -1 | 1) => void;
  onJointStop: () => void;
  onStop: () => void;
  onEnableControl: () => void;
  onSpeed: (percent: number) => void;
  onJogMode: (mode: JogMode) => void;
  onModel: (model: string | null) => void;
  onHome: () => void;
  /** Directions currently held by a controller. */
  heldDirections?: readonly Direction[];
  /** A pad is connected; the extra hint can mention it. */
  controllerConnected?: boolean;
}

const CARTESIAN: { axis: Axis; sign: -1 | 1; label: string }[] = [
  { axis: "x", sign: -1, label: "X −" },
  { axis: "x", sign: 1, label: "X +" },
  { axis: "y", sign: -1, label: "Y −" },
  { axis: "y", sign: 1, label: "Y +" },
  { axis: "z", sign: -1, label: "Z −" },
  { axis: "z", sign: 1, label: "Z +" },
];

const JOINTS: { axis: JointName; direction: -1 | 1; label: string }[] = [
  { axis: "shoulder", direction: -1, label: "Shoulder −" },
  { axis: "shoulder", direction: 1, label: "Shoulder +" },
  { axis: "elbow", direction: -1, label: "Elbow −" },
  { axis: "elbow", direction: 1, label: "Elbow +" },
];

function cartesianVector(axis: Axis, sign: -1 | 1): [-1 | 0 | 1, -1 | 0 | 1, -1 | 0 | 1] {
  if (axis === "x") return [sign, 0, 0];
  if (axis === "y") return [0, sign, 0];
  return [0, 0, sign];
}

function HoldButton({
  label,
  disabled,
  onStart,
  onStop,
}: {
  label: string;
  disabled: boolean;
  onStart: () => void;
  onStop: () => void;
}) {
  const down = useRef(false);
  const stopRef = useRef(onStop);
  stopRef.current = onStop;
  useEffect(
    () => () => {
      if (!down.current) return;
      down.current = false;
      stopRef.current();
    },
    [],
  );
  const press = () => {
    if (disabled || down.current) return;
    down.current = true;
    onStart();
  };
  const release = () => {
    if (!down.current) return;
    down.current = false;
    onStop();
  };
  return (
    <button
      type="button"
      className="axisbtn"
      aria-label={label}
      disabled={disabled}
      onPointerDown={(event) => {
        event.currentTarget.setPointerCapture?.(event.pointerId);
        press();
      }}
      onPointerUp={release}
      onPointerCancel={release}
      onLostPointerCapture={release}
      onKeyDown={(event) => {
        if (event.key !== " " && event.key !== "Enter") return;
        event.preventDefault();
        press();
      }}
      onKeyUp={(event) => {
        if (event.key === " " || event.key === "Enter") release();
      }}
    >
      {label}
    </button>
  );
}

const PAD: { direction: Direction; icon: React.ReactNode; area: string }[] = [
  { direction: "up", icon: <ArrowUp size={22} />, area: "up" },
  { direction: "left", icon: <ArrowLeft size={22} />, area: "left" },
  { direction: "right", icon: <ArrowRight size={22} />, area: "right" },
  { direction: "down", icon: <ArrowDown size={22} />, area: "down" },
];

function formatAge(age: number | null): string {
  if (age === null) return "never";
  if (age < 1) return `${Math.round(age * 1000)} ms ago`;
  return `${age.toFixed(1)} s ago`;
}

function Counts({ label, values, age }: { label: string; values: number[] | null; age: number | null }) {
  const stale = age === null || age > 2;
  return (
    <div className="telemetry__row">
      <div className="telemetry__head">
        <span>{label}</span>
        <span className={stale ? "telemetry__age is-stale" : "telemetry__age"}>{formatAge(age)}</span>
      </div>
      <code className="telemetry__values">{values ? values.join("  ") : "—"}</code>
    </div>
  );
}

function TelemetryCard({ telemetry }: { telemetry: Telemetry | null }) {
  if (!telemetry) {
    return <p className="muted">This robot's publisher does not report telemetry.</p>;
  }
  return (
    <>
      <Counts label="Joints (TELP)" values={telemetry.joint_counts} age={telemetry.joint_age_s} />
      <Counts label="Encoders (TEL)" values={telemetry.encoder_counts} age={telemetry.encoder_age_s} />
    </>
  );
}

export function DebugRail({
  status,
  onMoveStart,
  onMoveStop,
  onCartesianStart,
  onCartesianStop,
  onJointStart,
  onJointStop,
  onStop,
  onEnableControl,
  onSpeed,
  onJogMode,
  onModel,
  onHome,
  heldDirections = [],
  controllerConnected = false,
}: Props) {
  const selected = status.view.selected_host;
  const host = selected ? status.connections[selected] : undefined;
  const held = useRef(new Set<Direction>());
  const connected = Boolean(host?.open);
  const jogDisabled = !connected || Boolean(host?.auto_tracking);
  const reportedSpeed = status.speed_percent;
  const [speed, setSpeed] = useState(reportedSpeed ?? 20);
  const speedRef = useRef(speed);
  speedRef.current = speed;
  useEffect(() => {
    if (reportedSpeed != null) setSpeed(reportedSpeed);
  }, [reportedSpeed]);
  const commitSpeed = () => onSpeed(speedRef.current);

  const press = (direction: Direction) => {
    if (jogDisabled || held.current.has(direction)) return;
    held.current.add(direction);
    onMoveStart(direction);
  };
  const release = (direction: Direction) => {
    if (!held.current.delete(direction)) return;
    onMoveStop(direction);
  };

  // Never leave the robot moving if the rail unmounts mid-press.
  useEffect(() => {
    const pressed = held.current;
    return () => {
      pressed.forEach((direction) => onMoveStop(direction));
      pressed.clear();
    };
  }, [onMoveStop]);

  return (
    <aside className="rail" aria-label="Debug controls">
      <section className="rail__section">
        <h3>
          <Gauge size={16} /> Manual jog
        </h3>
        {host?.auto_tracking && <p className="muted">Turn off Auto-Track to jog manually.</p>}
        <div className="jogpad" aria-label="Jog pad">
          {PAD.map(({ direction, icon, area }) => (
            <button
              key={direction}
              type="button"
              className={`jogpad__btn${heldDirections.includes(direction) ? " is-held" : ""}`}
              style={{ gridArea: area }}
              aria-label={`Jog ${direction}`}
              aria-pressed={heldDirections.includes(direction) || undefined}
              disabled={jogDisabled}
              onPointerDown={(event) => {
                event.currentTarget.setPointerCapture?.(event.pointerId);
                press(direction);
              }}
              onPointerUp={() => release(direction)}
              onPointerCancel={() => release(direction)}
              onLostPointerCapture={() => release(direction)}
              onKeyDown={(event) => (event.key === " " || event.key === "Enter") && press(direction)}
              onKeyUp={(event) => (event.key === " " || event.key === "Enter") && release(direction)}
            >
              {icon}
            </button>
          ))}
          <button
            type="button"
            className="jogpad__btn jogpad__home"
            style={{ gridArea: "home" }}
            aria-label="Home"
            disabled={!host?.open}
            onClick={onHome}
          >
            <House size={20} />
          </button>
        </div>
        <Rocker<JogMode>
          label="Jog style"
          value={status.jog_mode}
          onChange={onJogMode}
          size="sm"
          options={JOG_OPTIONS}
        />

        <div className="axisblock">
          <h4>Cartesian</h4>
          <div className="axisgrid">
            {CARTESIAN.map(({ axis, sign, label }) => (
              <HoldButton
                key={label}
                label={label}
                disabled={jogDisabled}
                onStart={() => onCartesianStart(...cartesianVector(axis, sign))}
                onStop={onCartesianStop}
              />
            ))}
          </div>
          <p className="hint">Y − extends the arm. Y + retracts it.</p>
        </div>

        <div className="axisblock">
          <h4>Joints</h4>
          <div className="axisgrid">
            {JOINTS.map(({ axis, direction, label }) => (
              <HoldButton
                key={label}
                label={label}
                disabled={jogDisabled}
                onStart={() => onJointStart(axis, direction)}
                onStop={onJointStop}
              />
            ))}
          </div>
          <button type="button" className="axisbtn axisbtn--line" disabled={!connected} onClick={onEnableControl}>
            Enable control
          </button>
          <button type="button" className="axisbtn axisbtn--line" disabled={!connected} onClick={onStop}>
            Stop
          </button>
        </div>

        <div className="slider rail__speed">
          <div className="slider__head">
            <span>Speed</span>
            <span className="slider__value">
              {speed}%{reportedSpeed == null ? <code>not sent</code> : null}
            </span>
          </div>
          <input
            type="range"
            className="slider__input"
            aria-label="Manual speed"
            aria-valuemin={1}
            aria-valuemax={100}
            aria-valuetext={`${speed} percent`}
            min={1}
            max={100}
            step={1}
            value={speed}
            disabled={!connected}
            style={{ "--fill": `${((speed - 1) / 99) * 100}%` } as React.CSSProperties}
            onChange={(event) => {
              const next = Number(event.target.value);
              speedRef.current = next;
              setSpeed(next);
            }}
            onPointerUp={commitSpeed}
            onKeyUp={commitSpeed}
            onBlur={commitSpeed}
          />
          <p className="hint">Operator speed for manual moves. Home keeps its own speed.</p>
        </div>

        <p className="hint">
          {controllerConnected
            ? "Left stick aims. Right stick moves the shoulder and elbow. Triggers extend and retract. LB and RB switch cameras."
            : "Hold a button or an arrow key."}
        </p>
      </section>

      <section className="rail__section">
        <h3>
          <Box size={16} /> Detection
        </h3>
        <div className="field">
          <span className="field__row">
            <span>Model</span>
            {status.tracking.model ? (
              <button type="button" className="linkbtn" onClick={() => onModel(null)} title="Stop detection">
                Unload
              </button>
            ) : (
              <span className="muted">not loaded</span>
            )}
          </span>
          <ModelSlider
            label="Detection model"
            options={status.tracking.model_options}
            value={status.tracking.model}
            fallback={status.tracking.default_model ?? undefined}
            onChange={onModel}
          />
        </div>
        <dl className="stats">
          <div>
            <dt>Frames in</dt>
            <dd>{status.tracking.input_fps} fps</dd>
          </div>
          <div>
            <dt>Boxes out</dt>
            <dd>{status.tracking.output_fps} fps</dd>
          </div>
          <div>
            <dt>Subjects</dt>
            <dd>{host?.subjects ?? 0}</dd>
          </div>
        </dl>
      </section>

      <section className="rail__section">
        <h3>
          <Radio size={16} /> Telemetry {selected ? <span className="muted">· {selected}</span> : null}
        </h3>
        <TelemetryCard telemetry={host?.telemetry ?? null} />
      </section>

      <section className="rail__section rail__section--placeholder">
        <h3>Digital twin</h3>
        <p className="muted">3D twin view will live here.</p>
      </section>
    </aside>
  );
}
