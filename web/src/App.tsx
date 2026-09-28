import { X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { ActionBar } from "./components/ActionBar";
import { DebugRail } from "./components/DebugRail";
import { SettingsPanel } from "./components/SettingsPanel";
import { TopBar } from "./components/TopBar";
import { VideoStage } from "./components/VideoStage";
import { useCommand, useToasts } from "./hooks/useCommand";
import { useStatus } from "./hooks/useStatus";
import type { Direction, DisplayMode, JogMode, OneScreenMode, Slot, Status, UIMode } from "./types";

const ARROWS: Record<string, Direction> = {
  ArrowUp: "up",
  ArrowDown: "down",
  ArrowLeft: "left",
  ArrowRight: "right",
};

function isTyping(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName);
}

export default function App() {
  const { status, error, starting, refresh, setStatus } = useStatus();
  const { toasts, push, dismiss } = useToasts();
  const run = useCommand(push, refresh);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const applyStatus = useCallback(
    async (action: () => Promise<Status>) => {
      const next = await run(action);
      if (next) setStatus(next);
    },
    [run, setStatus],
  );

  const selectedHost = status?.view.selected_host ?? undefined;
  const selected = selectedHost ? status?.connections[selectedHost] : undefined;

  const onDisplayMode = (display_mode: DisplayMode) => applyStatus(() => api.setView({ display_mode }));
  const onOneScreenMode = (one_screen_mode: OneScreenMode) => applyStatus(() => api.setView({ one_screen_mode }));
  const onUIMode = (ui_mode: UIMode) => applyStatus(() => api.setView({ ui_mode }));
  const onSelectSlot = useCallback((slot: Slot) => applyStatus(() => api.select({ slot })), [applyStatus]);
  const onSelectHost = (host: string) => applyStatus(() => api.select({ host }));
  const onHome = useCallback(() => run(() => api.home(selectedHost)), [run, selectedHost]);
  const onAutoTrack = useCallback(
    (enabled: boolean) => run(() => api.setAutoTrack(enabled, selectedHost)),
    [run, selectedHost],
  );
  const onVirtualCamera = useCallback(
    (enabled: boolean) => run(() => api.setVirtualCamera(enabled)),
    [run],
  );
  const onMoveStart = useCallback((direction: Direction) => void run(() => api.moveStart(direction)), [run]);
  const onMoveStop = useCallback((direction: Direction) => void run(() => api.moveStop(direction)), [run]);
  const onJogMode = (mode: JogMode) => void run(() => api.setJogMode(mode));
  const onModel = (model: string | null) => void run(() => api.setModel(model));

  const heldKeys = useRef(new Set<Direction>());
  const keyState = useRef({ status, selected, settingsOpen });
  keyState.current = { status, selected, settingsOpen };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const { status: s, selected: host, settingsOpen: blocked } = keyState.current;
      if (!s || blocked || event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return;
      const direction = ARROWS[event.key];
      if (direction) {
        if (s.view.ui_mode !== "debug" || !host?.open || host.auto_tracking) return;
        event.preventDefault();
        if (!event.repeat && !heldKeys.current.has(direction)) {
          heldKeys.current.add(direction);
          onMoveStart(direction);
        }
        return;
      }
      if (event.repeat) return;
      const key = event.key.toLowerCase();
      if (key === "h" && host?.open) void onHome();
      else if (key === "t" && host?.open && !host.manual_only) void onAutoTrack(!host.auto_tracking);
      else if (key === "v" && (host?.has_video || s.virtual_camera)) void onVirtualCamera(!s.virtual_camera);
      else if ((key === "1" || key === "2") && s.view.available_slots === 2) {
        const slot = Number(key) as Slot;
        const manualOneScreen = s.view.display_mode === "one_screen" && s.view.one_screen_mode === "manual";
        if (manualOneScreen || s.view.display_mode === "two_screen") void onSelectSlot(slot);
      }
    };
    const onKeyUp = (event: KeyboardEvent) => {
      const direction = ARROWS[event.key];
      if (direction && heldKeys.current.delete(direction)) onMoveStop(direction);
    };
    const releaseAll = () => {
      heldKeys.current.forEach((direction) => onMoveStop(direction));
      heldKeys.current.clear();
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", releaseAll);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", releaseAll);
    };
  }, [onHome, onAutoTrack, onVirtualCamera, onSelectSlot, onMoveStart, onMoveStop]);

  const debug = status?.view.ui_mode === "debug";

  return (
    <div className={`shell ${debug ? "shell--debug" : ""}`}>
      <TopBar
        status={status}
        offline={error}
        onDisplayMode={onDisplayMode}
        onOneScreenMode={onOneScreenMode}
        onSelectSlot={onSelectSlot}
        onUIMode={onUIMode}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      {status ? (
        <>
          <main className="main">
            <VideoStage status={status} onSelectHost={onSelectHost} onOpenSettings={() => setSettingsOpen(true)} />
            {debug && (
              <DebugRail
                status={status}
                onMoveStart={onMoveStart}
                onMoveStop={onMoveStop}
                onJogMode={onJogMode}
                onModel={onModel}
                onHome={() => void onHome()}
              />
            )}
          </main>
          {status.view.available_slots > 0 && (
            <ActionBar
              status={status}
              onHome={onHome}
              onAutoTrack={onAutoTrack}
              onVirtualCamera={onVirtualCamera}
            />
          )}
        </>
      ) : (
        <main className="main main--loading">
          {starting ? (
            <div className="loading" role="status">
              <span className="loading__spinner" aria-hidden="true" />
              <strong>Connecting to cameras…</strong>
              <span className="muted">Commander is opening the robot and camera connections.</span>
            </div>
          ) : (
            <p className="muted">{error ?? "Connecting to Commander…"}</p>
          )}
        </main>
      )}

      <SettingsPanel
        open={settingsOpen}
        modelOptions={status?.tracking.model_options ?? []}
        onClose={() => setSettingsOpen(false)}
        onChanged={() => void refresh()}
      />

      <div className="toasts" aria-live="polite">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast--${toast.tone}`} role="status">
            <span>{toast.message}</span>
            <button type="button" className="iconbtn" aria-label="Dismiss" onClick={() => dismiss(toast.id)}>
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
