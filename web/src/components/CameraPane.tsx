import { Crosshair, VideoOff, WifiOff } from "lucide-react";
import { useEffect, useState } from "react";
import { mjpegUrl } from "../api";
import type { HostStatus, Slot } from "../types";

interface Props {
  host: string;
  slot: Slot | null;
  status: HostStatus | undefined;
  selected: boolean;
  selectable: boolean;
  onSelect?: () => void;
}

const RETRY_MS = 1500;

export function CameraPane({ host, slot, status, selected, selectable, onSelect }: Props) {
  const [attempt, setAttempt] = useState(0);
  const hasVideo = status?.has_video ?? false;

  // Restart the MJPEG request when the feed comes (back) online.
  useEffect(() => {
    if (hasVideo) setAttempt((n) => n + 1);
  }, [hasVideo]);

  const tracking = status?.auto_tracking ?? false;
  const className = [
    "pane",
    selectable ? "pane--selectable" : "",
    selected ? "pane--selected" : "",
    tracking ? "pane--tracking" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <figure className={className} data-testid={`pane-${host}`} aria-label={`Camera ${slot ?? ""} ${host}`}>
      {hasVideo ? (
        <img
          key={attempt}
          className="pane__video"
          src={`${mjpegUrl(host)}?r=${attempt}`}
          alt={`Live feed from ${host}`}
          onError={() => window.setTimeout(() => setAttempt((n) => n + 1), RETRY_MS)}
        />
      ) : (
        <div className="pane__nosignal" role="status">
          {status?.open ? <VideoOff size={40} strokeWidth={1.5} /> : <WifiOff size={40} strokeWidth={1.5} />}
          <strong>{status?.open ? "No signal" : "Not connected"}</strong>
          <span>{status?.open ? "Waiting for the camera stream…" : "Check the camera URL in Settings."}</span>
        </div>
      )}
      {selectable && (
        <button
          type="button"
          className="pane__hit"
          onClick={onSelect}
          aria-pressed={selected}
          aria-label={`Control camera ${slot ?? ""} (${host})`}
        />
      )}
      <figcaption className="pane__caption">
        <span className="pane__label">
          <span className="pane__slot">{slot ? `CAM ${slot}` : "CAM"}</span>
          <span className="pane__host">{host}</span>
          {selected && <span className="pane__controlling">Controlling</span>}
        </span>
        {tracking && (
          <span className="pane__badge" title="Auto-tracking is steering this camera">
            <Crosshair size={14} /> Tracking
            {status?.subjects ? ` · ${status.subjects}` : ""}
          </span>
        )}
      </figcaption>
    </figure>
  );
}
