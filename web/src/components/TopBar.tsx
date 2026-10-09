import { Hand, Settings, Shuffle, Wrench, X } from "lucide-react";
import type { OneScreenMode, Slot, Status, UIMode } from "../types";
import { Rocker } from "./Rocker";
import { Segmented } from "./Segmented";

interface Props {
  status: Status | null;
  offline: string | null;
  onOneScreenMode: (mode: OneScreenMode) => void;
  onSelectSlot: (slot: Slot) => void;
  onUIMode: (mode: UIMode) => void;
  onOpenSettings: () => void;
}

export function TopBar({ status, offline, onOneScreenMode, onSelectSlot, onUIMode, onOpenSettings }: Props) {
  const view = status?.view;
  const twoCameras = view?.available_slots === 2;

  return (
    <header className="topbar">
      <div className="brand">
        <svg viewBox="0 0 32 32" aria-hidden="true" className="brand__mark">
          <circle cx="16" cy="16" r="8" />
          <path d="M16 3v6M16 23v6M3 16h6M23 16h6" />
        </svg>
        <span className="brand__name">Commander</span>
      </div>

      <div className="topbar__right">
        {offline && (
          <span className="chip chip--danger" role="alert">
            {offline}
          </span>
        )}
        {view?.ui_mode === "debug" && (
          <button
            type="button"
            className="chip chip--debug"
            onClick={() => onUIMode("simple")}
            title="Leave debug mode (switch back to Simple)"
          >
            <Wrench size={13} /> Debug <X size={13} aria-hidden="true" />
          </button>
        )}

        {view && twoCameras && (
          <nav className="viewbar" aria-label="View">
            {view.one_screen_mode === "manual" ? (
              <Segmented<Slot>
                label="Controlled camera"
                value={view.displayed_slot ?? 1}
                onChange={onSelectSlot}
                size="sm"
                options={[
                  { value: 1, label: "Cam 1", title: `${view.camera_1} (key 1)` },
                  { value: 2, label: "Cam 2", title: `${view.camera_2} (key 2)` },
                ]}
              />
            ) : (
              <span className="viewbar__note">Controlling Cam {view.displayed_slot} · auto-switch coming soon</span>
            )}
            <Rocker<OneScreenMode>
              label="Camera switching"
              value={view.one_screen_mode}
              onChange={onOneScreenMode}
              size="sm"
              options={[
                { value: "manual", label: <><Hand size={14} /> Manual</>, description: "You choose the camera" },
                {
                  value: "dynamic",
                  label: <><Shuffle size={14} /> Dynamic</>,
                  description: "Commander picks the camera (switching logic coming in a later release)",
                },
              ]}
            />
          </nav>
        )}

        {status && (
          <button type="button" className="iconbtn" onClick={onOpenSettings} aria-label="Settings" title="Settings">
            <Settings size={20} />
          </button>
        )}
      </div>
    </header>
  );
}
