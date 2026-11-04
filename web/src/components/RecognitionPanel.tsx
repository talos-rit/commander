import { ScanFace } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { RecognitionStatus, ZoomStatus } from "../types";

interface Props {
  recognition: RecognitionStatus | undefined;
  /** The selected camera's zoom, for how its target was last recognized. */
  zoom: ZoomStatus | null | undefined;
  onLeniency: (leniency: number) => void;
  onForget: () => void;
}

function describeLeniency(percent: number): string {
  if (percent < 35) return "Strict";
  if (percent > 65) return "Lenient";
  return "Balanced";
}

function describeMatching(recognition: RecognitionStatus): string {
  if (recognition.faces && recognition.appearance) return "Face + body";
  if (recognition.faces) return "Face";
  if (recognition.appearance) return "Body";
  return "Position only";
}

function describeTarget(zoom: ZoomStatus | null | undefined): string | null {
  if (!zoom || zoom.target === null) return null;
  if (!zoom.match) return `#${zoom.target} not recognized on a return yet`;
  return `#${zoom.target} last recognized by ${zoom.match.by} · ${zoom.match.score.toFixed(2)}`;
}

export function RecognitionPanel({ recognition, zoom, onLeniency, onForget }: Props) {
  const reported = recognition ? Math.round(recognition.leniency * 100) : 50;
  const [percent, setPercent] = useState(reported);
  const percentRef = useRef(percent);
  percentRef.current = percent;
  useEffect(() => setPercent(reported), [reported]);
  const commit = () => {
    if (percentRef.current !== reported) onLeniency(percentRef.current / 100);
  };

  if (!recognition) {
    return (
      <section className="rail__section" aria-label="Recognition">
        <h3>
          <ScanFace size={16} /> Recognition
        </h3>
        <p className="muted">This backend does not report recognition.</p>
      </section>
    );
  }

  const target = describeTarget(zoom);
  return (
    <section className="rail__section" aria-label="Recognition">
      <h3>
        <ScanFace size={16} /> Recognition <span className="muted">· {describeMatching(recognition)}</span>
      </h3>
      <div className="slider rail__speed">
        <div className="slider__head">
          <span className="slider__value">{describeLeniency(percent)}</span>
          <span className="slider__scale">fewer mix-ups ← → more recognized</span>
        </div>
        <input
          type="range"
          className="slider__input"
          aria-label="Recognition leniency"
          aria-valuetext={`${describeLeniency(percent)}, ${percent} percent lenient`}
          min={0}
          max={100}
          step={5}
          value={percent}
          style={{ "--fill": `${percent}%` } as React.CSSProperties}
          onChange={(event) => {
            const next = Number(event.target.value);
            percentRef.current = next;
            setPercent(next);
          }}
          onPointerUp={commit}
          onKeyUp={commit}
          onBlur={commit}
        />
      </div>
      <dl className="stats">
        <div>
          <dt>Known</dt>
          <dd>{recognition.known}</dd>
        </div>
      </dl>
      {target && <p className="hint">{target}</p>}
      <button type="button" className="btn" onClick={onForget} disabled={recognition.known === 0}>
        Forget everyone
      </button>
      <p className="hint">
        Strict mixes people up less, but may give someone who comes back a new number. Nothing is saved to disk.
      </p>
    </section>
  );
}
