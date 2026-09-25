import { Crosshair, House, Link2, Link2Off, LoaderCircle, ScanFace, Video, VideoOff } from "lucide-react";
import { useEffect, useState } from "react";
import type { HostStatus, Status } from "../types";

interface Props {
  status: Status;
  onHome: () => Promise<unknown>;
  onAutoTrack: (enabled: boolean) => Promise<unknown>;
}

const HOMING_FEEDBACK_MS = 2000;

function StatusChip({ ok, on, off, label }: { ok: boolean; on: React.ReactNode; off: React.ReactNode; label: string }) {
  return (
    <span className={`chip ${ok ? "chip--ok" : "chip--warn"}`} title={label}>
      {ok ? on : off}
    </span>
  );
}

export function ActionBar({ status, onHome, onAutoTrack }: Props) {
  const selected = status.view.selected_host;
  const host: HostStatus | undefined = selected ? status.connections[selected] : undefined;
  const [homing, setHoming] = useState(false);
  const [pendingTrack, setPendingTrack] = useState(false);

  useEffect(() => {
    if (!homing) return;
    const id = window.setTimeout(() => setHoming(false), HOMING_FEEDBACK_MS);
    return () => window.clearTimeout(id);
  }, [homing]);

  const ready = Boolean(host?.open);
  const tracking = host?.auto_tracking ?? false;
  const trackDisabled = !ready || host?.manual_only || pendingTrack;
  const trackTitle = host?.manual_only
    ? "This robot is configured as manual only"
    : tracking
      ? "Stop auto-tracking (T)"
      : "Start auto-tracking the subject (T)";

  const home = async () => {
    setHoming(true);
    await onHome();
  };

  const toggleTracking = async () => {
    setPendingTrack(true);
    try {
      await onAutoTrack(!tracking);
    } finally {
      setPendingTrack(false);
    }
  };

  return (
    <footer className="actionbar">
      <div className="actionbar__target">
        {selected ? (
          <>
            <span className="target">
              <span className="target__label">Controlling</span>
              <span className="target__host">
                {host?.slot ? `CAM ${host.slot} · ` : ""}
                {selected}
              </span>
            </span>
            <StatusChip
              ok={host?.operator_connected ?? false}
              on={<><Link2 size={14} /> Robot linked</>}
              off={<><Link2Off size={14} /> Robot offline</>}
              label="Connection to the robot's Operator"
            />
            <StatusChip
              ok={host?.has_video ?? false}
              on={<><Video size={14} /> Video</>}
              off={<><VideoOff size={14} /> No video</>}
              label="Camera stream"
            />
            {status.tracking.model && (
              <span className="chip" title="Detection model used for tracking">
                <ScanFace size={14} /> {status.tracking.model}
              </span>
            )}
          </>
        ) : (
          <span className="target target--none">No robot selected</span>
        )}
      </div>

      <div className="actionbar__actions">
        <button
          type="button"
          className="action action--home"
          onClick={home}
          disabled={!ready || homing}
          title="Send the robot to its home position (H)"
        >
          {homing ? <LoaderCircle className="spin" size={26} /> : <House size={26} />}
          <span>{homing ? "Homing…" : "Home"}</span>
        </button>
        <button
          type="button"
          className={`action action--track ${tracking ? "is-on" : ""}`}
          onClick={toggleTracking}
          disabled={trackDisabled}
          aria-pressed={tracking}
          title={trackTitle}
        >
          <span className="action__icon">
            <Crosshair size={26} />
          </span>
          <span className="action__text">
            <span>Auto-Track</span>
            <small>{host?.manual_only ? "Manual only" : tracking ? "On" : "Off"}</small>
          </span>
        </button>
      </div>
    </footer>
  );
}
