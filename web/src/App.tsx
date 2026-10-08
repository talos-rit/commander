import { X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { ActionBar } from "./components/ActionBar";
import { DebugRail } from "./components/DebugRail";
import { SettingsPanel } from "./components/SettingsPanel";
import { TopBar } from "./components/TopBar";
import { VideoStage } from "./components/VideoStage";
import { describeController, DIRECTION_ORDER, type ArmCommand, type ControllerGate, type PadAction } from "./gamepad";
import { useCommand, useToasts } from "./hooks/useCommand";
import { useGamepad } from "./hooks/useGamepad";
import { useStatus } from "./hooks/useStatus";
import type { Direction, DisplayMode, JogMode, OneScreenMode, Slot, Status, UIMode } from "./types";

const ARROWS: Record<string, Direction> = {
  ArrowUp: "up",
  ArrowDown: "down",
  ArrowLeft: "left",
  ArrowRight: "right",
};

/** Right bumper steps forward and left bumper steps back, wrapping past either end. */
function slotAfterBumper(current: Slot, side: "left" | "right"): Slot {
  if (side === "right") return current === 2 ? 1 : 2;
  return current === 1 ? 2 : 1;
}

function selectedSlot(status: Status): Slot {
  const { camera_1, camera_2, selected_host, displayed_slot } = status.view;
  if (selected_host && selected_host === camera_2) return 2;
  if (selected_host && selected_host === camera_1) return 1;
  return displayed_slot === 2 ? 2 : 1;
}

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
  const onPiVision = useCallback(
    (enabled: boolean) => run(() => api.setPiVisionPerception(enabled, selectedHost)),
    [run, selectedHost],
  );
  const onVirtualCamera = useCallback(
    (enabled: boolean) => run(() => api.setVirtualCamera(enabled)),
    [run],
  );
  const onPiTolerance = useCallback(
    (ratio: number) => run(() => api.setPiVisionTolerance(ratio, selectedHost)),
    [run, selectedHost],
  );
  const onMoveStart = useCallback((direction: Direction) => void run(() => api.moveStart(direction)), [run]);
  const onMoveStop = useCallback((direction: Direction) => void run(() => api.moveStop(direction)), [run]);
  const onJointStart = useCallback(
    (axis: "shoulder" | "elbow", direction: -1 | 1) => void run(() => api.jointStart(axis, direction)),
    [run],
  );
  const onJointStop = useCallback(() => void run(() => api.jointStop()), [run]);
  const onCartesianStart = useCallback(
    (y: -1 | 1) => void run(() => api.cartesianStart(0, y, 0)),
    [run],
  );
  const onCartesianStop = useCallback(() => void run(() => api.cartesianStop()), [run]);
  const onJogMode = (mode: JogMode) => void run(() => api.setJogMode(mode));
  const onModel = (model: string | null) => void run(() => api.setModel(model));

  const debug = status?.view.ui_mode === "debug";
  const robotReady = Boolean(selected?.open);
  const jogEnabled = Boolean(debug && robotReady && !selected?.auto_tracking && !settingsOpen);
  const bumpersEnabled = Boolean(
    status &&
      !settingsOpen &&
      status.view.available_slots === 2 &&
      (status.view.display_mode === "two_screen" ||
        (status.view.display_mode === "one_screen" && status.view.one_screen_mode === "manual")),
  );
  const keyHeld = useRef(new Set<Direction>());
  const padHeld = useRef(new Set<Direction>());
  const jogged = useRef(new Set<Direction>());
  // Keys and the controller share one jog. Releasing one does not stop a direction the other still holds.
  const syncJog = useCallback(() => {
    const next = new Set<Direction>([...keyHeld.current, ...padHeld.current]);
    for (const direction of DIRECTION_ORDER) {
      if (jogged.current.has(direction) && !next.has(direction)) onMoveStop(direction);
    }
    for (const direction of DIRECTION_ORDER) {
      if (!jogged.current.has(direction) && next.has(direction)) onMoveStart(direction);
    }
    jogged.current = next;
  }, [onMoveStart, onMoveStop]);
  const jointSent = useRef<ArmCommand["joint"]>(null);
  const extensionSent = useRef<ArmCommand["y"]>(0);
  const syncArm = useCallback(
    (arm: ArmCommand) => {
      const previous = jointSent.current;
      const next = arm.joint;
      if (previous?.axis !== next?.axis || previous?.direction !== next?.direction) {
        if (next) onJointStart(next.axis, next.direction);
        else onJointStop();
        jointSent.current = next;
      }
      if (extensionSent.current !== arm.y) {
        if (arm.y === 0) onCartesianStop();
        else onCartesianStart(arm.y);
        extensionSent.current = arm.y;
      }
    },
    [onCartesianStart, onCartesianStop, onJointStart, onJointStop],
  );
  const slotRef = useRef<Slot>(1);
  const pendingSlot = useRef<Slot | null>(null);
  const statusSlot = status ? selectedSlot(status) : null;
  const keyState = useRef({ status, selected, settingsOpen });
  keyState.current = { status, selected, settingsOpen };
  const onPadAction = (action: PadAction) => {
    const { status: viewStatus, selected: host, settingsOpen: blocked } = keyState.current;
    if (!viewStatus || blocked) return;
    if (action === "menu") void onUIMode(viewStatus.view.ui_mode === "debug" ? "simple" : "debug");
    else if (action === "back" && host?.open) void onHome();
    else if (action === "y") void onOneScreenMode(viewStatus.view.one_screen_mode === "manual" ? "dynamic" : "manual");
    else if (action === "x" && (viewStatus.virtual_camera || (host?.open && host.has_video))) {
      void onVirtualCamera(!viewStatus.virtual_camera);
    } else if (action === "b" && viewStatus.view.available_slots === 2) {
      void onDisplayMode(viewStatus.view.display_mode === "two_screen" ? "one_screen" : "two_screen");
    } else if (action === "a" && host?.open && !host.manual_only) void onAutoTrack(!host.auto_tracking);
  };
  useEffect(() => {
    if (statusSlot == null) return;
    if (pendingSlot.current !== null && pendingSlot.current !== statusSlot) return;
    slotRef.current = statusSlot;
    pendingSlot.current = null;
  }, [statusSlot]);
  const gamepad = useGamepad({
    jog: jogEnabled,
    bumpers: bumpersEnabled,
    actions: Boolean(status && !settingsOpen),
    onDirections: (directions) => {
      padHeld.current = new Set(directions);
      syncJog();
    },
    onArm: syncArm,
    onBumper: (side) => {
      const next = slotAfterBumper(slotRef.current, side);
      slotRef.current = next;
      pendingSlot.current = next;
      void onSelectSlot(next);
    },
    onAction: onPadAction,
  });
  const controllerGate: ControllerGate | null = !gamepad.pad
    ? null
    : !gamepad.pad.mapped
      ? "unmapped"
      : settingsOpen
        ? "settings"
        : !debug
          ? "debug"
          : selected?.auto_tracking
            ? "tracking"
            : !robotReady
              ? "offline"
              : "ready";

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const { status: s, selected: host, settingsOpen: blocked } = keyState.current;
      if (!s || blocked || event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return;
      const direction = ARROWS[event.key];
      if (direction) {
        if (s.view.ui_mode !== "debug" || !host?.open || host.auto_tracking) return;
        event.preventDefault();
        if (!event.repeat && !keyHeld.current.has(direction)) {
          keyHeld.current.add(direction);
          syncJog();
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
      if (direction && keyHeld.current.delete(direction)) syncJog();
    };
    const releaseAll = () => {
      if (keyHeld.current.size === 0) return;
      keyHeld.current.clear();
      syncJog();
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", releaseAll);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", releaseAll);
    };
  }, [onHome, onAutoTrack, onVirtualCamera, onSelectSlot, syncJog]);

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
                heldDirections={gamepad.held}
                controllerConnected={Boolean(gamepad.pad)}
              />
            )}
          </main>
          {status.view.available_slots > 0 && (
            <ActionBar
              status={status}
              onHome={onHome}
              onClearError={() => run(() => api.clearRobotError(selectedHost))}
              onAutoTrack={onAutoTrack}
              onPiVision={onPiVision}
              onPiTolerance={onPiTolerance}
              onVirtualCamera={onVirtualCamera}
              controller={
                gamepad.pad && controllerGate
                  ? {
                      label: gamepad.pad.label,
                      driving: controllerGate === "ready",
                      title: describeController(controllerGate),
                    }
                  : null
              }
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
