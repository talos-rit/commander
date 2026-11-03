import { Crosshair, Gamepad2, House, Link2, Link2Off, LoaderCircle, ScanFace, Video, VideoOff, Webcam } from "lucide-react";
import { useState } from "react";
import type { CommandReceipt, HostStatus, Status } from "../types";
import { CenteringTolerance } from "./CenteringTolerance";

interface Props {
  status: Status;
  onHome: () => Promise<unknown>;
  onClearError?: () => Promise<unknown>;
  onAutoTrack: (enabled: boolean) => Promise<unknown>;
  onPiVision?: (enabled: boolean) => Promise<unknown>;
  onPiTolerance?: (ratio: number) => Promise<unknown>;
  onVirtualCamera: (enabled: boolean) => Promise<unknown>;
  /** A connected gamepad, when the browser has reported one. */
  controller?: { label: string; driving: boolean; title: string } | null;
}

const RECEIPT_VISIBLE_S = 8;
const RECEIPT_WAIT_S = 1.5;

/** Operator's ACK means the frame was queued. Hide it once that moment has passed. */
export function commandReceiptChip(receipt: CommandReceipt | null | undefined): { text: string; tone: string; title: string } | null {
  if (!receipt || (receipt.sent === 0 && !receipt.last_failed)) return null;
  const name = receipt.last_command;
  const sentAge = receipt.last_sent_age_s;
  const ackAge = receipt.last_ack_age_s;
  const pending = receipt.acked !== null && receipt.acked < receipt.sent;
  const failed = receipt.last_failed && !pending && (ackAge == null || (sentAge != null && sentAge <= ackAge));
  const withName = (label: string) => (name ? `${name} · ${label}` : label);

  if (failed) {
    if (sentAge != null && sentAge > RECEIPT_VISIBLE_S) return null;
    return { text: withName("Not sent"), tone: "chip--danger", title: "The command did not leave this machine." };
  }
  if (receipt.acked === null) {
    if (sentAge == null || sentAge > RECEIPT_VISIBLE_S) return null;
    return {
      text: withName("Sent"),
      tone: "chip--ok",
      title: "The Pi accepted the command. This link does not report Operator's acknowledgement.",
    };
  }
  if (pending) {
    if (sentAge == null || sentAge > RECEIPT_VISIBLE_S) return null;
    if (sentAge < RECEIPT_WAIT_S) {
      return {
        text: withName("Waiting"),
        tone: "chip--warn",
        title: "Waiting for Operator to acknowledge this command. The acknowledgement means the frame was queued.",
      };
    }
    return {
      text: withName("No receipt"),
      tone: "chip--warn",
      title: "The command was written out. Operator sent no acknowledgement.",
    };
  }
  if (ackAge != null && ackAge <= RECEIPT_VISIBLE_S) {
    return {
      text: withName("Received"),
      tone: "chip--ok",
      title: "Operator queued this command. The arm may still be moving.",
    };
  }
  return null;
}

/** Floats over the bottom of the debug column so the status chips never reflow. */
export function CommandReceipt({ status }: { status: Status }) {
  const host = status.view.selected_host ? status.connections[status.view.selected_host] : undefined;
  const receipt = commandReceiptChip(host?.command);
  if (!receipt) return null;
  const tone = receipt.tone === "chip--danger" ? "error" : receipt.tone === "chip--warn" ? "warn" : "ok";
  return (
    <div className={`receipt-toast toast toast--${tone}`} role="status" title={receipt.title}>
      <span>{receipt.text}</span>
    </div>
  );
}

function StatusChip({ ok, on, off, label }: { ok: boolean; on: React.ReactNode; off: React.ReactNode; label: string }) {
  return (
    <span className={`chip ${ok ? "chip--ok" : "chip--warn"}`} title={label}>
      {ok ? on : off}
    </span>
  );
}

export function ActionBar({ status, onHome, onClearError, onAutoTrack, onPiVision, onPiTolerance, onVirtualCamera, controller = null }: Props) {
  const selected = status.view.selected_host;
  const host: HostStatus | undefined = selected ? status.connections[selected] : undefined;
  const [sendingHome, setSendingHome] = useState(false);
  const [pendingTrack, setPendingTrack] = useState(false);
  const [pendingCamera, setPendingCamera] = useState(false);
  const [clearingError, setClearingError] = useState(false);

  const ready = Boolean(host?.open);
  const tracking = host?.auto_tracking ?? false;
  const trackDisabled = !ready || host?.manual_only || pendingTrack;
  const trackTitle = host?.manual_only
    ? "This robot is configured as manual only"
    : tracking
      ? "Stop auto-tracking (T)"
      : "Start auto-tracking the subject (T)";

  const home = async () => {
    setSendingHome(true);
    try {
      await onHome();
    } finally {
      setSendingHome(false);
    }
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
            {host?.pi_vision?.robot_fault ? (
              <span role="status" className="chip chip--danger" title={host.pi_vision.robot_fault}>Robot error</span>
            ) : <StatusChip
              ok={host?.operator_connected ?? false}
              on={<><Link2 size={14} /> Robot linked</>}
              off={<><Link2Off size={14} /> Robot offline</>}
              label="Connection to the robot's Operator"
            />}
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
                title={host.pi_vision.error ?? undefined}>
                PiVision · {host.pi_vision.state ?? (host.pi_vision.inference_s == null ? "waiting" : `${Math.round(host.pi_vision.inference_s * 1000)} ms`)}
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

      {host?.pi_vision && onPiTolerance && (
        <CenteringTolerance key={selected} ratio={host.pi_vision.acceptable_ratio ?? .25} onChange={onPiTolerance} />
      )}
      <div className="actionbar__actions">
        {host?.pi_vision && onClearError && (
          <button type="button" className="btn" disabled={!ready || clearingError}
            onClick={async () => {
              setClearingError(true);
              try { await onClearError(); }
              finally { setClearingError(false); }
            }}>
            {clearingError ? "Clearing…" : "Clear error"}
          </button>
        )}
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
          disabled={!ready || sendingHome}
          title="Send the robot to its home position (H)"
        >
          {sendingHome ? <LoaderCircle className="spin" size={26} /> : <House size={26} />}
          <span>{sendingHome ? "Sending…" : "Home"}</span>
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
