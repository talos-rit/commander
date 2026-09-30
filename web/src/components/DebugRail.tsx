import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Box, Gauge, House, Radio } from "lucide-react";
import { useEffect, useRef } from "react";
import type { Direction, JogMode, Status, Telemetry } from "../types";
import { ModelSlider } from "./ModelSlider";
import { Rocker, type RockerOption } from "./Rocker";

export const JOG_OPTIONS: readonly [RockerOption<JogMode>, RockerOption<JogMode>] = [
  { value: "discrete", label: "Discrete", description: "Sends repeated step commands while held" },
  { value: "continuous", label: "Continuous", description: "Moves smoothly until you release" },
];

interface Props {
  status: Status;
  onMoveStart: (direction: Direction) => void;
  onMoveStop: (direction: Direction) => void;
  onJogMode: (mode: JogMode) => void;
  onModel: (model: string | null) => void;
  onHome: () => void;
  /** Directions currently held by a controller. */
  heldDirections?: readonly Direction[];
  /** A pad is connected; the extra hint can mention it. */
  controllerConnected?: boolean;
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
  onJogMode,
  onModel,
  onHome,
  heldDirections = [],
  controllerConnected = false,
}: Props) {
  const selected = status.view.selected_host;
  const host = selected ? status.connections[selected] : undefined;
  const held = useRef(new Set<Direction>());
  const jogDisabled = !host?.open || host.auto_tracking;

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
