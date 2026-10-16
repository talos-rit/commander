import { ScanSearch } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { HostStatus, Subject } from "../types";

interface Props {
  host: HostStatus | undefined;
  /** A local detection model is loaded, so subjects can be listed. */
  modelLoaded: boolean;
  /** PiVision steers the arm on the Pi, so it does not follow the zoom subject. */
  piVision?: boolean;
  onTarget: (trackId: number | null) => void;
  onFill: (fill: number) => void;
}

const FILL_MIN = 20;
const FILL_MAX = 90;

function describe(zoom: NonNullable<HostStatus["zoom"]>): string {
  if (zoom.target === null) return "Full frame";
  if (zoom.locked) return `Following #${zoom.target} · ${zoom.level.toFixed(1)}×`;
  if (zoom.holding) return `#${zoom.target} lost · holding`;
  return `#${zoom.target} out of view · full frame`;
}

function SubjectRow({
  label,
  detail,
  checked,
  disabled,
  onSelect,
}: {
  label: string;
  detail?: string;
  checked: boolean;
  disabled?: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={checked}
      className={`subject${checked ? " is-active" : ""}`}
      disabled={disabled}
      onClick={onSelect}
    >
      <span className="subject__label">{label}</span>
      {detail ? <span className="subject__detail">{detail}</span> : null}
    </button>
  );
}

function subjectDetail(subject: Subject): string {
  const [x1, y1, x2, y2] = subject.box;
  const size = `${x2 - x1}×${y2 - y1}`;
  return subject.confidence === null ? size : `${Math.round(subject.confidence * 100)}% · ${size}`;
}

export function ZoomPanel({ host, modelLoaded, piVision = false, onTarget, onFill }: Props) {
  const zoom = host?.zoom ?? null;
  const subjects = host?.subject_list ?? [];
  const reportedFill = zoom ? Math.round(zoom.fill * 100) : 60;
  const [fill, setFill] = useState(reportedFill);
  const fillRef = useRef(fill);
  fillRef.current = fill;
  useEffect(() => setFill(reportedFill), [reportedFill]);
  const commitFill = () => {
    if (fillRef.current !== reportedFill) onFill(fillRef.current / 100);
  };

  const target = zoom?.target ?? null;
  const targetMissing = target !== null && !subjects.some((subject) => subject.id === target);
  const usable = Boolean(host?.open && zoom);

  return (
    <section className="rail__section" aria-label="Zoom">
      <h3>
        <ScanSearch size={16} /> Zoom {zoom ? <span className="muted">· {describe(zoom)}</span> : null}
      </h3>
      {!host?.open ? (
        <p className="muted">Connect a camera to zoom.</p>
      ) : !zoom ? (
        <p className="muted">This backend does not report zoom.</p>
      ) : !modelLoaded ? (
        <p className="muted">
          {piVision ? "Turn on PiVision perception to list subjects." : "Load a detection model to list subjects."}
        </p>
      ) : null}

      {usable && (
        <>
          <div className="subjects" role="radiogroup" aria-label="Zoom subject">
            <SubjectRow label="Full frame" checked={target === null} onSelect={() => onTarget(null)} />
            {subjects.map((subject, index) => (
              <SubjectRow
                key={subject.id ?? `untracked-${index}`}
                label={subject.id === null ? "Untracked" : `Subject #${subject.id}`}
                detail={subjectDetail(subject)}
                checked={subject.id !== null && subject.id === target}
                disabled={subject.id === null}
                onSelect={() => subject.id !== null && onTarget(subject.id)}
              />
            ))}
            {targetMissing && (
              <SubjectRow label={`Subject #${target}`} detail="out of view" checked disabled onSelect={() => {}} />
            )}
          </div>
          {modelLoaded && subjects.length === 0 && <p className="hint">No subjects in view.</p>}

          <div className="slider rail__speed">
            <div className="slider__head">
              <span>Subject fills</span>
              <span className="slider__value">{fill}%</span>
            </div>
            <input
              type="range"
              className="slider__input"
              aria-label="Subject fill"
              aria-valuetext={`${fill} percent of the frame`}
              min={FILL_MIN}
              max={FILL_MAX}
              step={5}
              value={fill}
              style={{ "--fill": `${((fill - FILL_MIN) / (FILL_MAX - FILL_MIN)) * 100}%` } as React.CSSProperties}
              onChange={(event) => {
                const next = Number(event.target.value);
                fillRef.current = next;
                setFill(next);
              }}
              onPointerUp={commitFill}
              onKeyUp={commitFill}
              onBlur={commitFill}
            />
          </div>
          <p className="hint">
            Digital zoom crops the feed and the virtual camera.{" "}
            {piVision
              ? "PiVision still picks who the arm follows."
              : "Auto-Track follows the chosen subject."}
          </p>
        </>
      )}
    </section>
  );
}
