import { useEffect, useRef, useState } from "react";
import {
  armFromGamepads,
  bumpersPressed,
  connectedGamepads,
  DIRECTION_ORDER,
  directionsFromGamepads,
  IDLE_ARM,
  presenceFromGamepads,
  probeGamepads,
  type ArmCommand,
  type ArmHold,
  type ControllerPresence,
  type GamepadProbe,
  type HatState,
} from "../gamepad";
import type { Direction } from "../types";

export interface GamepadHandlers {
  /** Manual jog is allowed (debug mode, robot ready, not tracking, settings closed). */
  jog: boolean;
  /** LB / RB may switch the selected camera. */
  bumpers: boolean;
  /** Directions the pad currently wants. Empty when it is idle, blocked, or gone. */
  onDirections: (directions: readonly Direction[]) => void;
  /** Shoulder, elbow, and extend/retract. Idle when jog is blocked or the pad is gone. */
  onArm: (arm: ArmCommand) => void;
  onBumper: (side: "left" | "right") => void;
}

export interface GamepadState {
  pad: ControllerPresence | null;
  held: readonly Direction[];
  probes: GamepadProbe[];
  secure: boolean;
}

function readGamepads(): ArrayLike<Gamepad | null> {
  try {
    return navigator.getGamepads?.() ?? [];
  } catch {
    return [];
  }
}

function probesKey(probes: GamepadProbe[]): string {
  return probes
    .map((probe) => `${probe.index}:${probe.mapping}:${probe.pressed.join(".")}:${probe.axes.join(",")}`)
    .join("|");
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
  const suppressBumpers = useRef(false);
  const padRef = useRef<ControllerPresence | null>(null);
  const heldKey = useRef("");
  const probesRef = useRef("");
  const connectedRef = useRef(false);

  const [pad, setPad] = useState<ControllerPresence | null>(null);
  const [heldList, setHeldList] = useState<readonly Direction[]>([]);
  const [probes, setProbes] = useState<GamepadProbe[]>([]);
  const [secure] = useState(() => window.isSecureContext !== false);

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

      const nextProbes = probeGamepads(list);
      const key = probesKey(nextProbes);
      if (key !== probesRef.current) {
        probesRef.current = key;
        setProbes(nextProbes);
      }

      const pageAsleep = blurred.current || document.hidden;
      if (!connected.length || pageAsleep || !latest.current.jog) {
        reportRef.current([]);
        releaseArm();
      } else {
        reportRef.current(directionsFromGamepads(list, held.current, hats.current));
        armReportRef.current(armFromGamepads(list, padIndex.current, armHold.current));
      }

      const physical = bumpersPressed(list);
      if (!connected.length || pageAsleep || suppressBumpers.current || !latest.current.bumpers) {
        bumpers.current = physical;
        if (!pageAsleep) suppressBumpers.current = false;
      } else {
        if (physical.left && !bumpers.current.left) latest.current.onBumper("left");
        if (physical.right && !bumpers.current.right) latest.current.onBumper("right");
        bumpers.current = physical;
      }
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
      suppressBumpers.current = true;
      reportRef.current([]);
      releaseArm();
    };
    const onFocus = () => {
      blurred.current = false;
    };
    const onVisibility = () => {
      if (document.hidden) {
        suppressBumpers.current = true;
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

  return { pad, held: heldList, probes, secure };
}
