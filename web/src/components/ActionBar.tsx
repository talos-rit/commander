import { Crosshair, Gamepad2, House, Link2, Link2Off, LoaderCircle, ScanFace, Video, VideoOff, Webcam } from "lucide-react";
import { useEffect, useState } from "react";
import type { HostStatus, Status } from "../types";

interface Props {
  status: Status;
  onHome: () => Promise<unknown>;
  onAutoTrack: (enabled: boolean) => Promise<unknown>;
  onPiVision?: (enabled: boolean) => Promise<unknown>;
  onVirtualCamera: (enabled: boolean) => Promise<unknown>;
  /** A connected gamepad, when the browser has reported one. */
  controller?: { label: string; driving: boolean; title: string } | null;
}

const HOMING_FEEDBACK_MS = 2000;

function StatusChip({ ok, on, off, label }: { ok: boolean; on: React.ReactNode; off: React.ReactNode; label: string }) {
  return (
    <span className={`chip ${ok ? "chip--ok" : "chip--warn"}`} title={label}>
      {ok ? on : off}
    </span>
  );
}

export function ActionBar({ status, onHome, onAutoTrack, onPiVision, onVirtualCamera, controller = null }: Props) {
  const selected = status.view.selected_host;
  const host: HostStatus | undefined = selected ? status.connections[selected] : undefined;
  const [homing, setHoming] = useState(false);
  const [pendingTrack, setPendingTrack] = useState(false);
  const [pendingCamera, setPendingCamera] = useState(false);

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

  const streaming = status.virtual_camera;
  const cameraDisabled = pendingCamera || (!streaming && (!ready || !host?.has_video));
  const cameraTitle = streaming
    ? "Stop sending the selected camera to the virtual webcam (V)"
    : !ready || !host?.has_video
      ? "Waiting for a camera frame to stream"
      : "Send the selected camera to a virtual webcam, for OBS or Zoom to record (V)";

  const toggleCamera = async () => {
    setPendingCamera(true);
    try {
      await onVirtualCamera(!streaming);
    } finally {
      setPendingCamera(false);
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
            {status.tracking.model && !host?.pi_vision && (
              <span className="chip" title="Detection model used for tracking">
                <ScanFace size={14} /> {status.tracking.model}
              </span>
            )}
            {host?.pi_vision && (
              <span className={`chip ${host.pi_vision.error ? "chip--warn" : "chip--ok"}`}
                title={host.pi_vision.error ?? "PiVision detects and tracks locally; Commander supervises"}>
                PiVision · {host.pi_vision.inference_s == null ? "waiting" : `${Math.round(host.pi_vision.inference_s * 1000)} ms`}
              </span>
            )}
            {controller && (
              <span
                className={`chip chip--pad ${controller.driving ? "chip--ok" : "chip--warn"}`}
                title={controller.title}
              >
                <Gamepad2 size={14} />
                <span className="chip__text">{controller.label}</span>
              </span>
            )}
          </>
        ) : (
          <span className="target target--none">No robot selected</span>
        )}
      </div>

      <div className="actionbar__actions">
        {host?.pi_vision && onPiVision && (
          <button type="button" className="btn" disabled={pendingTrack}
            onClick={async () => {
              setPendingTrack(true);
              try { await onPiVision(!host.pi_vision?.perception_enabled); }
              finally { setPendingTrack(false); }
            }}>
            {host.pi_vision.perception_enabled ? "Pause PiVision" : "Resume PiVision"}
          </button>
        )}
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
        <button
          type="button"
          className={`action action--cam ${streaming ? "is-on" : ""}`}
          onClick={toggleCamera}
          disabled={cameraDisabled}
          aria-pressed={streaming}
          title={cameraTitle}
        >
          <span className="action__icon">
            {pendingCamera ? <LoaderCircle className="spin" size={26} /> : <Webcam size={26} />}
          </span>
          <span className="action__text">
            <span>Virtual Cam</span>
            <small>{streaming ? "On" : "Off"}</small>
          </span>
        </button>
      </div>
    </footer>
  );
}
