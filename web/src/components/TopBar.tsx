import { Columns2, Hand, RectangleHorizontal, Settings, Shuffle, Wrench, X } from "lucide-react";
import type { DisplayMode, OneScreenMode, Slot, Status, UIMode } from "../types";
import { Rocker } from "./Rocker";
import { Segmented } from "./Segmented";

interface Props {
  status: Status | null;
  offline: string | null;
  onDisplayMode: (mode: DisplayMode) => void;
  onOneScreenMode: (mode: OneScreenMode) => void;
  onSelectSlot: (slot: Slot) => void;
  onUIMode: (mode: UIMode) => void;
  onOpenSettings: () => void;
}

export const TWO_SCREEN_DISABLED_REASON =
  "Two-screen mode needs two cameras. Only one is assigned — pick a Camera 2 in Settings to enable it.";

export function TopBar({ status, offline, onDisplayMode, onOneScreenMode, onSelectSlot, onUIMode, onOpenSettings }: Props) {
  const view = status?.view;
  const twoCameras = view?.available_slots === 2;
  const oneScreen = view?.display_mode === "one_screen";

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

        {view && view.available_slots > 0 && (
          <nav className="viewbar" aria-label="View">
            {twoCameras && oneScreen && (
              <>
                {view.one_screen_mode === "manual" ? (
                  <Segmented<Slot>
                    label="Camera shown"
                    value={view.displayed_slot ?? 1}
                    onChange={onSelectSlot}
                    size="sm"
                    options={[
                      { value: 1, label: "Cam 1", title: `${view.camera_1} (key 1)` },
                      { value: 2, label: "Cam 2", title: `${view.camera_2} (key 2)` },
                    ]}
                  />
                ) : (
                  <span className="viewbar__note">Showing Cam {view.displayed_slot} · auto-switch coming soon</span>
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
                <span className="viewbar__divider" aria-hidden="true" />
              </>
            )}
            <Rocker<DisplayMode>
              label="Screen layout"
              value={view.display_mode}
              onChange={onDisplayMode}
              disabled={!twoCameras}
              disabledReason={TWO_SCREEN_DISABLED_REASON}
              options={[
                {
                  value: "one_screen",
                  label: <><RectangleHorizontal size={16} /> One screen</>,
                  description: "Show one camera at a time",
                },
                {
                  value: "two_screen",
                  label: <><Columns2 size={16} /> Two screen</>,
                  description: "Show both cameras side by side",
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
