import { useEffect, useRef, useState } from "react";

interface Props {
  ratio: number;
  onChange: (ratio: number) => Promise<unknown>;
}

export function CenteringTolerance({ ratio, onChange }: Props) {
  const [draft, setDraft] = useState<number | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const revision = useRef(0);
  useEffect(() => () => {
    revision.current += 1;
    if (timer.current !== null) clearTimeout(timer.current);
  }, []);

  const change = (percent: number) => {
    setDraft(percent);
    if (timer.current !== null) clearTimeout(timer.current);
    const current = ++revision.current;
    timer.current = setTimeout(() => {
      timer.current = null;
      void onChange(percent / 100).catch(() => undefined).finally(() => {
        if (revision.current === current) setDraft(null);
      });
    }, 250);
  };
  const percent = draft ?? Math.round(ratio * 100);
  return (
    <label className="centering-tolerance">
      <span>Centering tolerance <output>{percent}%</output></span>
      <input aria-label="Centering tolerance" type="range" min={5} max={80} step={1}
        value={percent} onChange={(event) => change(Number(event.target.value))} />
    </label>
  );
}
