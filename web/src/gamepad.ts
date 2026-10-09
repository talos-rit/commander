import type { Direction } from "./types";

/** Standard Gamepad API indexes. Xbox and matching third-party pads use these. */
export const FACE_A = 0;
export const FACE_B = 1;
export const FACE_X = 2;
export const FACE_Y = 3;
export const BUMPER_LEFT = 4;
export const BUMPER_RIGHT = 5;
export const TRIGGER_LEFT = 6;
export const TRIGGER_RIGHT = 7;
export const BUTTON_BACK = 8;
export const BUTTON_MENU = 9;
export const DPAD_UP = 12;
export const DPAD_DOWN = 13;
export const DPAD_LEFT = 14;
export const DPAD_RIGHT = 15;

/**
 * Left-stick deflection that starts a jog, and the lower value that keeps it
 * going. The gap stops a stick resting on the threshold from chattering.
 */
export const STICK_ENGAGE = 0.45;
export const STICK_RELEASE = 0.28;

export const DIRECTION_ORDER: readonly Direction[] = ["up", "down", "left", "right"];

export interface ControllerPresence {
  label: string;
  mapped: boolean;
}

export type ControllerGate = "ready" | "debug" | "tracking" | "offline" | "settings" | "unmapped";

export function gamepadLabel(id: string): string {
  const cleaned = id.replace(/\s*\([^)]*\)/g, " ").replace(/\s+/g, " ").trim();
  return cleaned || "Controller";
}

export function describeController(gate: ControllerGate): string {
  switch (gate) {
    case "unmapped":
      return "This controller isn't using the standard Xbox layout. Its D-pad still jogs the robot; the stick and shoulder buttons need that layout.";
    case "settings":
      return "Controller connected. Close Settings to use it.";
    case "debug":
      return "Controller connected. Menu toggles Debug mode.";
    case "tracking":
      return "Controller connected. Turn off Auto-Track to jog.";
    case "offline":
      return "Controller connected. The selected robot isn't ready to move.";
    case "ready":
      return "Left stick and D-pad aim. Right stick jogs the shoulder and elbow, one joint at a time. Triggers extend and retract the arm. LB and RB switch cameras in Manual. Menu toggles Debug, Back homes, A toggles Auto-Track, X Virtual Cam, and Y Manual or Dynamic.";
  }
}

export function connectedGamepads(gamepads: ArrayLike<Gamepad | null>): Gamepad[] {
  const connected: Gamepad[] = [];
  for (let i = 0; i < gamepads.length; i += 1) {
    const pad = gamepads[i];
    if (pad?.connected) connected.push(pad);
  }
  return connected;
}

/**
 * Label/bumper pad: prefer the one already in use, then any standard-layout
 * pad. Directions are read from every connected listing — macOS Chrome often
 * exposes one physical controller twice, and the "standard" copy has a dead D-pad.
 */
export function selectGamepad(gamepads: ArrayLike<Gamepad | null>, preferredIndex: number | null): Gamepad | null {
  const connected = connectedGamepads(gamepads);
  const preferred = connected.find((pad) => pad.index === preferredIndex);
  if (preferred?.mapping === "standard") return preferred;
  return connected.find((pad) => pad.mapping === "standard") ?? preferred ?? connected[0] ?? null;
}

export function isButtonPressed(button: GamepadButton | number | undefined): boolean {
  if (button == null) return false;
  if (typeof button === "number") return button >= 0.5;
  return Boolean(button.pressed || button.value >= 0.5);
}

export function buttonPressed(gamepad: Gamepad, index: number): boolean {
  return isButtonPressed(gamepad.buttons[index]);
}

export function bumpersPressed(gamepads: ArrayLike<Gamepad | null>): { left: boolean; right: boolean } {
  let left = false;
  let right = false;
  for (const pad of connectedGamepads(gamepads)) {
    if (buttonPressed(pad, BUMPER_LEFT)) left = true;
    if (buttonPressed(pad, BUMPER_RIGHT)) right = true;
  }
  return { left, right };
}

export type PadAction = "a" | "b" | "x" | "y" | "back" | "menu";

const PAD_ACTION_INDEXES: Record<PadAction, number> = {
  a: FACE_A,
  b: FACE_B,
  x: FACE_X,
  y: FACE_Y,
  back: BUTTON_BACK,
  menu: BUTTON_MENU,
};

export const PAD_ACTIONS = Object.keys(PAD_ACTION_INDEXES) as PadAction[];

/** Face, Back, and Menu buttons across every listing. A HID duplicate can be the one that actually reports them. */
export function padActionsPressed(gamepads: ArrayLike<Gamepad | null>): Record<PadAction, boolean> {
  const pressed = { a: false, b: false, x: false, y: false, back: false, menu: false };
  for (const pad of connectedGamepads(gamepads)) {
    for (const action of PAD_ACTIONS) {
      if (buttonPressed(pad, PAD_ACTION_INDEXES[action])) pressed[action] = true;
    }
  }
  return pressed;
}

export function presenceFromGamepads(gamepads: ArrayLike<Gamepad | null>, preferredIndex: number | null): ControllerPresence | null {
  const connected = connectedGamepads(gamepads);
  if (connected.length === 0) return null;
  const display = selectGamepad(gamepads, preferredIndex) ?? connected[0];
  return {
    label: gamepadLabel(display.id),
    mapped: connected.some((pad) => pad.mapping === "standard"),
  };
}

/**
 * macOS browsers often leave the D-pad as a HID hat switch on an extra axis
 * (commonly axis 9) instead of buttons 12–15. Neutral sits at 9/7, outside the
 * normal stick range, and the eight directions step by 2/7 clockwise from up.
 */
const HAT_TOLERANCE = 0.06;
const HAT_NEUTRAL = 9 / 7;
const HAT_POSITIONS: readonly { value: number; directions: readonly Direction[] }[] = [
  { value: -1, directions: ["up"] },
  { value: -5 / 7, directions: ["up", "right"] },
  { value: -3 / 7, directions: ["right"] },
  { value: -1 / 7, directions: ["down", "right"] },
  { value: 1 / 7, directions: ["down"] },
  { value: 3 / 7, directions: ["down", "left"] },
  { value: 5 / 7, directions: ["left"] },
  { value: 1, directions: ["up", "left"] },
  { value: HAT_NEUTRAL, directions: [] },
];

export interface HatState {
  axis: number | null;
}

function matchHatValue(value: number): readonly Direction[] | null {
  if (!Number.isFinite(value)) return null;
  for (const position of HAT_POSITIONS) {
    if (Math.abs(value - position.value) <= HAT_TOLERANCE) return position.directions;
  }
  return null;
}

/** ±1 also belongs to triggers and sticks, so it only counts once an axis has proved it is a hat. */
function isAmbiguousHat(value: number): boolean {
  return Math.abs(Math.abs(value) - 1) <= HAT_TOLERANCE;
}

export function readHat(
  axes: ArrayLike<number>,
  knownAxis: number | null,
): { directions: readonly Direction[]; axis: number | null } {
  if (knownAxis !== null && knownAxis >= 4 && knownAxis < axes.length) {
    const directions = matchHatValue(axes[knownAxis]);
    if (directions) return { directions, axis: knownAxis };
    return { directions: [], axis: knownAxis };
  }

  for (let index = axes.length - 1; index >= 4; index -= 1) {
    const directions = matchHatValue(axes[index]);
    if (!directions || isAmbiguousHat(axes[index])) continue;
    return { directions, axis: index };
  }
  return { directions: [], axis: null };
}

function looksDigital(value: number): boolean {
  return Math.abs(value) <= 0.15 || Math.abs(Math.abs(value) - 1) <= 0.15;
}

function collect(target: Set<Direction>, directions: readonly Direction[]) {
  for (const direction of directions) target.add(direction);
}

/** Axes 6/7 are a two-axis D-pad on many HID listings. 4/5 are usually analog triggers. */
function dpadFromAxisPairs(axes: ArrayLike<number>, hatAxis: number | null, target: Set<Direction>) {
  if (axes.length < 8 || hatAxis === 6 || hatAxis === 7) return;
  const x = axes[6] ?? 0;
  const y = axes[7] ?? 0;
  if (!looksDigital(x) || !looksDigital(y)) return;
  if (x <= -0.5) target.add("left");
  else if (x >= 0.5) target.add("right");
  if (y <= -0.5) target.add("up");
  else if (y >= 0.5) target.add("down");
}

function axisDirection(
  value: number,
  negative: Direction,
  positive: Direction,
  dpadNegative: boolean,
  dpadPositive: boolean,
  held: ReadonlySet<Direction>,
): Direction | null {
  if (dpadNegative !== dpadPositive) return dpadPositive ? positive : negative;
  if (dpadNegative) return null;
  const threshold = held.has(negative) || held.has(positive) ? STICK_RELEASE : STICK_ENGAGE;
  if (!Number.isFinite(value) || Math.abs(value) < threshold) return null;
  return value < 0 ? negative : positive;
}

/**
 * Jog directions for one listing. Button D-pad, hat-switch, and extra digital
 * axes are read on any mapping. The left stick still needs the standard layout.
 * The D-pad wins over the stick on that axis.
 */
export function directionsFromGamepad(
  gamepad: Gamepad,
  held: ReadonlySet<Direction> = new Set(),
  hatState?: HatState,
): Direction[] {
  const hat = readHat(gamepad.axes, hatState?.axis ?? null);
  if (hatState) hatState.axis = hat.axis;
  const dpad = new Set<Direction>(hat.directions);
  if (buttonPressed(gamepad, DPAD_UP)) dpad.add("up");
  if (buttonPressed(gamepad, DPAD_DOWN)) dpad.add("down");
  if (buttonPressed(gamepad, DPAD_LEFT)) dpad.add("left");
  if (buttonPressed(gamepad, DPAD_RIGHT)) dpad.add("right");
  dpadFromAxisPairs(gamepad.axes, hat.axis, dpad);

  const standard = gamepad.mapping === "standard";
  const chosen = new Set<Direction>();
  const horizontal = axisDirection(
    standard ? (gamepad.axes[0] ?? 0) : 0,
    "left",
    "right",
    dpad.has("left"),
    dpad.has("right"),
    held,
  );
  const vertical = axisDirection(
    standard ? (gamepad.axes[1] ?? 0) : 0,
    "up",
    "down",
    dpad.has("up"),
    dpad.has("down"),
    held,
  );
  if (horizontal) chosen.add(horizontal);
  if (vertical) chosen.add(vertical);
  return DIRECTION_ORDER.filter((direction) => chosen.has(direction));
}

export function directionsFromGamepads(
  gamepads: ArrayLike<Gamepad | null>,
  held: ReadonlySet<Direction>,
  hats: Map<number, HatState>,
): Direction[] {
  const connected = connectedGamepads(gamepads);
  const chosen = new Set<Direction>();
  const seen = new Set<number>();
  for (const pad of connected) {
    seen.add(pad.index);
    let hat = hats.get(pad.index);
    if (!hat) {
      hat = { axis: null };
      hats.set(pad.index, hat);
    }
    collect(chosen, directionsFromGamepad(pad, held, hat));
  }
  for (const index of [...hats.keys()]) {
    if (!seen.has(index)) hats.delete(index);
  }
  return DIRECTION_ORDER.filter((direction) => chosen.has(direction));
}

export type JointAxis = "shoulder" | "elbow";

/** Right-stick joint and trigger extension. Wrist roll (the claw) is left unmapped. */
export interface ArmCommand {
  joint: { axis: JointAxis; direction: -1 | 1 } | null;
  /** Cartesian Y. -1 extends away from the base, +1 retracts, 0 holds still. */
  y: -1 | 0 | 1;
}

export const IDLE_ARM: ArmCommand = { joint: null, y: 0 };

export interface ArmHold {
  joint: JointAxis | null;
  retract: boolean;
  extend: boolean;
  /** Axes that rest near -1, keyed `${padIndex}:${axis}`. Sticks rest at 0 and are not recorded. */
  negativeRest: Set<string>;
  /** Axes already seen near 0, so a later slam to -1 is a stick, not a trigger waking up. */
  centered: Set<string>;
}

const RIGHT_STICK_X = 2;
const RIGHT_STICK_Y = 3;
const TRIGGER_AXIS_LEFT = 4;
const TRIGGER_AXIS_RIGHT = 5;

function buttonPull(button: GamepadButton | number | undefined): number {
  if (button == null) return 0;
  if (typeof button === "number") return button >= 0.5 ? 1 : Math.max(0, button);
  const value = Number.isFinite(button.value) ? Math.max(0, button.value) : 0;
  // Some pads report a digital trigger as pressed while leaving value at 0.
  return button.pressed ? Math.max(value, 1) : value;
}

/**
 * HID triggers often rest at -1 and reach 0 or +1 when pulled. A stick rests at 0,
 * so an axis only becomes a trigger after it has sat near -1 without first sitting at 0.
 * `allowPositive` is for axes 4/5, which are triggers even when they rest at 0.
 */
function axisPull(pad: Gamepad, axisIndex: number, allowPositive: boolean, held: ArmHold): number {
  const value = pad.axes[axisIndex];
  if (!Number.isFinite(value)) return 0;
  const key = `${pad.index}:${axisIndex}`;
  if (Math.abs(value) <= 0.15) held.centered.add(key);
  else if (value <= -0.85 && !held.centered.has(key)) held.negativeRest.add(key);
  if (held.negativeRest.has(key)) return Math.min(1, Math.max(0, (value + 1) / 2));
  if (!allowPositive) return 0;
  return Math.min(1, Math.max(0, value));
}

function triggerPair(pad: Gamepad, held: ArmHold): { retract: number; extend: number } {
  const standard = pad.mapping === "standard";
  // Button indexes are only meaningful on the standard listing. On the HID duplicate
  // those same indexes are often Back and Start.
  let retract = standard ? buttonPull(pad.buttons[TRIGGER_LEFT]) : 0;
  let extend = standard ? buttonPull(pad.buttons[TRIGGER_RIGHT]) : 0;
  retract = Math.max(retract, axisPull(pad, TRIGGER_AXIS_LEFT, true, held));
  extend = Math.max(extend, axisPull(pad, TRIGGER_AXIS_RIGHT, true, held));
  if (!standard) {
    retract = Math.max(retract, axisPull(pad, RIGHT_STICK_X, false, held));
    extend = Math.max(extend, axisPull(pad, RIGHT_STICK_Y, false, held));
  }
  return { retract, extend };
}

function pulled(value: number, already: boolean): boolean {
  return value >= (already ? STICK_RELEASE : STICK_ENGAGE);
}

/**
 * Shoulder is the right stick's sideways axis, elbow is up and down.
 * The hardware jog moves one joint, so a diagonal keeps the joint already
 * held unless the other axis is clearly stronger.
 */
function jointFromStick(x: number, y: number, held: JointAxis | null): ArmCommand["joint"] {
  const shoulderHeld = held === "shoulder";
  const elbowHeld = held === "elbow";
  const shoulderMag = Math.abs(x);
  const elbowMag = Math.abs(y);
  const shoulderOn = Number.isFinite(x) && shoulderMag >= (shoulderHeld ? STICK_RELEASE : STICK_ENGAGE);
  const elbowOn = Number.isFinite(y) && elbowMag >= (elbowHeld ? STICK_RELEASE : STICK_ENGAGE);
  let axis: JointAxis | null = null;
  if (shoulderOn && elbowOn) {
    if (shoulderHeld && shoulderMag + 0.12 >= elbowMag) axis = "shoulder";
    else if (elbowHeld && elbowMag + 0.12 >= shoulderMag) axis = "elbow";
    else axis = shoulderMag >= elbowMag ? "shoulder" : "elbow";
  } else if (shoulderOn) axis = "shoulder";
  else if (elbowOn) axis = "elbow";
  if (axis === "shoulder") return { axis, direction: x < 0 ? -1 : 1 };
  if (axis === "elbow") return { axis, direction: y < 0 ? 1 : -1 };
  return null;
}

function ensureTriggerMemory(held: ArmHold) {
  held.negativeRest ??= new Set();
  held.centered ??= new Set();
}

/**
 * The right stick comes from the standard listing. Triggers are merged across
 * every listing: macOS Chrome often leaves buttons 6 and 7 dead on the standard
 * copy and reports LT/RT as axes on the HID duplicate.
 */
export function armFromGamepads(
  gamepads: ArrayLike<Gamepad | null>,
  preferredIndex: number | null,
  held: ArmHold,
): ArmCommand {
  ensureTriggerMemory(held);
  const connected = connectedGamepads(gamepads);
  const standard = selectGamepad(gamepads, preferredIndex);
  const joint =
    standard?.mapping === "standard"
      ? jointFromStick(standard.axes[RIGHT_STICK_X] ?? 0, standard.axes[RIGHT_STICK_Y] ?? 0, held.joint)
      : null;
  let retractPull = 0;
  let extendPull = 0;
  const seen = new Set<number>();
  for (const pad of connected) {
    seen.add(pad.index);
    const pair = triggerPair(pad, held);
    retractPull = Math.max(retractPull, pair.retract);
    extendPull = Math.max(extendPull, pair.extend);
  }
  for (const key of [...held.negativeRest, ...held.centered]) {
    const index = Number(key.slice(0, key.indexOf(":")));
    if (!seen.has(index)) {
      held.negativeRest.delete(key);
      held.centered.delete(key);
    }
  }
  const retract = pulled(retractPull, held.retract);
  const extend = pulled(extendPull, held.extend);
  held.joint = joint?.axis ?? null;
  held.retract = retract;
  held.extend = extend;
  let y: -1 | 0 | 1 = 0;
  if (extend !== retract) y = extend ? -1 : 1;
  return { joint, y };
}

export function armFromGamepad(gamepad: Gamepad | null, held: ArmHold): ArmCommand {
  return armFromGamepads(gamepad ? [gamepad] : [], gamepad?.index ?? null, held);
}
