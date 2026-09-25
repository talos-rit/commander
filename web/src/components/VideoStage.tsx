import { Camera, Settings } from "lucide-react";
import type { Status } from "../types";
import { CameraPane } from "./CameraPane";

interface Props {
  status: Status;
  onSelectHost: (host: string) => void;
  onOpenSettings: () => void;
}

export function VideoStage({ status, onSelectHost, onOpenSettings }: Props) {
  const { view, connections } = status;

  if (view.available_slots === 0) {
    return (
      <section className="stage stage--empty">
        <div className="empty">
          <Camera size={48} strokeWidth={1.25} />
          <h2>No camera assigned</h2>
          <p>
            {status.robots.length > 0
              ? "Pick a robot to use as Camera 1."
              : "Add a robot with its operator address and camera stream to get started."}
          </p>
          <button type="button" className="btn btn--primary" onClick={onOpenSettings}>
            <Settings size={18} /> Open settings
          </button>
        </div>
      </section>
    );
  }

  const twoScreen = view.display_mode === "two_screen";
  return (
    <section className={`stage ${twoScreen ? "stage--two" : "stage--one"}`} aria-label="Camera feeds">
      {view.displayed_hosts.map((host) => (
        <CameraPane
          key={host}
          host={host}
          slot={connections[host]?.slot ?? null}
          status={connections[host]}
          selected={view.selected_host === host}
          selectable={twoScreen}
          onSelect={() => onSelectHost(host)}
        />
      ))}
    </section>
  );
}
