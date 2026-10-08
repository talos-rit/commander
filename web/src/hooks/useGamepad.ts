import { useEffect, useRef, useState } from "react";
import {
  armFromGamepads,
  bumpersPressed,
  connectedGamepads,
  DIRECTION_ORDER,
  directionsFromGamepads,
  IDLE_ARM,
  PAD_ACTIONS,
  padActionsPressed,
  presenceFromGamepads,
  type ArmCommand,
  type ArmHold,
  type ControllerPresence,
  type HatState,
  type PadAction,
} from "../gamepad";
import type { Direction } from "../types";

export interface GamepadHandlers {
  /** Manual jog is allowed (debug mode, robot ready, not tracking, settings closed). */
  jog: boolean;
  /** LB / RB may switch the selected camera. */
  bumpers: boolean;
  /** Menu, Back, and the face buttons may change view and robot mode. */
  actions: boolean;
  /** Directions the pad currently wants. Empty when it is idle, blocked, or gone. */
  onDirections: (directions: readonly Direction[]) => void;
  /** Shoulder, elbow, and wrist pitch. Idle when jog is blocked or the pad is gone. */
  onArm: (arm: ArmCommand) => void;
  onBumper: (side: "left" | "right") => void;
  onAction: (action: PadAction) => void;
}

export interface GamepadState {
  pad: ControllerPresence | null;
  held: readonly Direction[];
}

function readGamepads(): ArrayLike<Gamepad | null> {
  try {
    return navigator.getGamepads?.() ?? [];
  } catch {
    return [];
  }
}

/**
 * Polls the browser Gamepad API and turns Xbox-layout (and HID duplicate)
 * listings into the same jog and camera-switch commands as the keyboard.
 * Browsers hide a pad until a button is pressed. The API is a secure-context
 * feature: HTTPS, localhost, or 127.0.0.1 — not a random LAN http://IP.
 */
export function useGamepad(handlers: GamepadHandlers): GamepadState {
  const latest = useRef(handlers);
  latest.current = handlers;

  const held = useRef(new Set<Direction>());
  const bumpers = useRef({ left: false, right: false });
  const actions = useRef<Record<PadAction, boolean>>({
    a: false,
    b: false,
    x: false,
    y: false,
    back: false,
    menu: false,
  });
  const padIndex = useRef<number | null>(null);
  const hats = useRef(new Map<number, HatState>());
  const armHold = useRef<ArmHold>({
    joint: null,
    retract: false,
    extend: false,
    negativeRest: new Set(),
    centered: new Set(),
  });
  const armKey = useRef(":0:0");
  const blurred = useRef(false);
  const suppressEdges = useRef(false);
  const padRef = useRef<ControllerPresence | null>(null);
  const heldKey = useRef("");
  const connectedRef = useRef(false);

  const [pad, setPad] = useState<ControllerPresence | null>(null);
  const [heldList, setHeldList] = useState<readonly Direction[]>([]);

  const publishPad = (next: ControllerPresence | null) => {
    const prev = padRef.current;
    const same =
      (prev === null && next === null) ||
      (prev !== null && next !== null && prev.label === next.label && prev.mapped === next.mapped);
    if (same) return;
    padRef.current = next;
    setPad(next);
  };

  const report = (next: readonly Direction[]) => {
    const ordered = DIRECTION_ORDER.filter((direction) => next.includes(direction));
    const key = ordered.join(",");
    if (key === heldKey.current) return;
    heldKey.current = key;
    held.current = new Set(ordered);
    setHeldList(ordered);
    latest.current.onDirections(ordered);
  };
  const reportRef = useRef(report);
  reportRef.current = report;

  const reportArm = (next: ArmCommand) => {
    const key = `${next.joint?.axis ?? ""}:${next.joint?.direction ?? 0}:${next.y}`;
    if (key === armKey.current) return;
    armKey.current = key;
    latest.current.onArm(next);
  };
  const armReportRef = useRef(reportArm);
  armReportRef.current = reportArm;

  const releaseArm = () => {
    armHold.current.joint = null;
    armHold.current.retract = false;
    armHold.current.extend = false;
    armReportRef.current(IDLE_ARM);
  };

  useEffect(() => {
    if (!handlers.jog) {
      reportRef.current([]);
      armHold.current.joint = null;
      armHold.current.retract = false;
      armHold.current.extend = false;
      armReportRef.current(IDLE_ARM);
    }
  }, [handlers.jog]);

  useEffect(() => {
    let raf = 0;
    let stopped = false;

    const sample = () => {
      const list = readGamepads();
      const connected = connectedGamepads(list);
      connectedRef.current = connected.length > 0;
      const presence = presenceFromGamepads(list, padIndex.current);
      padIndex.current = connected.find((pad) => pad.index === padIndex.current)?.index ?? connected[0]?.index ?? null;
      publishPad(presence);

      const pageAsleep = blurred.current || document.hidden;
      if (!connected.length || pageAsleep || !latest.current.jog) {
        reportRef.current([]);
        releaseArm();
      } else {
        reportRef.current(directionsFromGamepads(list, held.current, hats.current));
        armReportRef.current(armFromGamepads(list, padIndex.current, armHold.current));
      }

      const physical = bumpersPressed(list);
      const padActions = padActionsPressed(list);
      const quiet = !connected.length || pageAsleep || suppressEdges.current;
      if (quiet || !latest.current.bumpers) {
        bumpers.current = physical;
      } else {
        if (physical.left && !bumpers.current.left) latest.current.onBumper("left");
        if (physical.right && !bumpers.current.right) latest.current.onBumper("right");
        bumpers.current = physical;
      }
      if (quiet || !latest.current.actions) {
        actions.current = padActions;
      } else {
        for (const action of PAD_ACTIONS) {
          if (padActions[action] && !actions.current[action]) latest.current.onAction(action);
        }
        actions.current = padActions;
      }
      if (!pageAsleep) suppressEdges.current = false;
    };

    let queued = false;
    const queue = () => {
      if (stopped || queued) return;
      queued = true;
      raf = requestAnimationFrame(() => {
        queued = false;
        sample();
        if (!stopped && connectedRef.current) queue();
      });
    };
    const onBlur = () => {
      blurred.current = true;
      suppressEdges.current = true;
      reportRef.current([]);
      releaseArm();
    };
    const onFocus = () => {
      blurred.current = false;
    };
    const onVisibility = () => {
      if (document.hidden) {
        suppressEdges.current = true;
        reportRef.current([]);
        releaseArm();
      }
    };
    const onDisconnect = () => {
      sample();
      queue();
    };

    window.addEventListener("blur", onBlur);
    window.addEventListener("focus", onFocus);
    window.addEventListener("gamepadconnected", queue);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("gamepaddisconnected", onDisconnect);
    queue();
    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("gamepadconnected", queue);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("gamepaddisconnected", onDisconnect);
      reportRef.current([]);
      releaseArm();
    };
  }, []);

  return { pad, held: heldList };
}
