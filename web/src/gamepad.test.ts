import { describe, expect, it } from "vitest";
import type { Direction } from "./types";
import {
  armFromGamepad,
  armFromGamepads,
  BUTTON_MENU,
  describeController,
  FACE_A,
  directionsFromGamepad,
  directionsFromGamepads,
  DPAD_DOWN,
  DPAD_LEFT,
  DPAD_RIGHT,
  DPAD_UP,
  gamepadLabel,
  padActionsPressed,
  selectGamepad,
  STICK_ENGAGE,
  STICK_RELEASE,
  TRIGGER_LEFT,
  TRIGGER_RIGHT,
  type ArmHold,
  type HatState,
} from "./gamepad";

function pad(overrides: Partial<Gamepad> = {}): Gamepad {
  return {
    id: "Xbox 360 Controller (STANDARD GAMEPAD Vendor: 045e Product: 028e)",
    index: 0,
    connected: true,
    mapping: "standard",
    timestamp: 0,
    axes: [0, 0, 0, 0],
    buttons: Array.from({ length: 17 }, () => ({ pressed: false, touched: false, value: 0 })),
    ...overrides,
  } as Gamepad;
}

function press(gamepad: Gamepad, index: number, value = 1) {
  const buttons = Array.from(gamepad.buttons);
  buttons[index] = { pressed: value >= 0.5, touched: true, value };
  return pad({ ...gamepad, buttons });
}

describe("gamepad layout", () => {
  it("strips the browser's vendor suffix from the controller name", () => {
    expect(gamepadLabel("Xbox 360 Controller (STANDARD GAMEPAD Vendor: 045e Product: 028e)")).toBe(
      "Xbox 360 Controller",
    );
    expect(gamepadLabel("   ")).toBe("Controller");
  });

  it("describes why a connected controller can or cannot drive", () => {
    expect(describeController("ready")).toMatch(/Left stick/);
    expect(describeController("debug")).toMatch(/Debug mode/);
    expect(describeController("tracking")).toMatch(/Auto-Track/);
    expect(describeController("offline")).toMatch(/isn't ready/);
    expect(describeController("settings")).toMatch(/Close Settings/);
    expect(describeController("unmapped")).toMatch(/standard Xbox layout/);
  });

  it("prefers the pad already in use, then any standard-layout pad", () => {
    const xbox = pad({ index: 0, id: "Xbox" });
    const other = pad({ index: 1, id: "Other" });
    const unknown = pad({ index: 2, id: "Arcade", mapping: "" });
    expect(selectGamepad([null, other, xbox], 1)).toBe(other);
    expect(selectGamepad([null, unknown, xbox], 2)?.id).toBe("Xbox");
    expect(selectGamepad([unknown], null)?.id).toBe("Arcade");
    expect(selectGamepad([null, null], 0)).toBeNull();
  });

  it("maps the left stick to pan and tilt, with a dead zone and hysteresis", () => {
    expect(directionsFromGamepad(pad({ axes: [0.2, 0, 0, 0] }))).toEqual([]);
    expect(directionsFromGamepad(pad({ axes: [STICK_ENGAGE, 0, 0, 0] }))).toEqual(["right"]);
    expect(directionsFromGamepad(pad({ axes: [-0.8, -0.8, 0.4, 0.4] }))).toEqual(["up", "left"]);
    expect(directionsFromGamepad(pad({ axes: [0, 0.9, 0, 0] }))).toEqual(["down"]);

    const heldRight = new Set<Direction>(["right"]);
    expect(directionsFromGamepad(pad({ axes: [STICK_RELEASE, 0, 0, 0] }), heldRight)).toEqual(["right"]);
    expect(directionsFromGamepad(pad({ axes: [STICK_RELEASE - 0.01, 0, 0, 0] }), heldRight)).toEqual([]);
  });

  it("lets the D-pad override the stick on that axis", () => {
    let gamepad = pad({ axes: [0.9, 0.9, 0, 0] });
    gamepad = press(gamepad, DPAD_UP);
    gamepad = press(gamepad, DPAD_LEFT);
    expect(directionsFromGamepad(gamepad)).toEqual(["up", "left"]);
  });

  it("ignores an axis when both D-pad directions are pressed", () => {
    let gamepad = pad({ axes: [0, -1, 0, 0] });
    gamepad = press(gamepad, DPAD_LEFT);
    gamepad = press(gamepad, DPAD_RIGHT);
    expect(directionsFromGamepad(gamepad)).toEqual(["up"]);
  });

  function hatAxes(value: number): number[] {
    const axes = Array.from({ length: 10 }, () => 0);
    axes[9] = value;
    return axes;
  }

  it("reads a macOS hat-switch D-pad that never lights buttons 12-15", () => {
    const hat: HatState = { axis: null };
    // Neutral is 9/7. Up is -1, which is ambiguous until this axis has identified itself.
    expect(directionsFromGamepad(pad({ axes: hatAxes(9 / 7) }), new Set(), hat)).toEqual([]);
    expect(hat.axis).toBe(9);
    expect(directionsFromGamepad(pad({ axes: hatAxes(-1) }), new Set(), hat)).toEqual(["up"]);
    expect(directionsFromGamepad(pad({ axes: hatAxes(1 / 7) }), new Set(), hat)).toEqual(["down"]);
    expect(directionsFromGamepad(pad({ axes: hatAxes(5 / 7) }), new Set(), hat)).toEqual(["left"]);
    expect(directionsFromGamepad(pad({ axes: hatAxes(-3 / 7) }), new Set(), hat)).toEqual(["right"]);
    expect(directionsFromGamepad(pad({ axes: hatAxes(-5 / 7) }), new Set(), hat)).toEqual(["up", "right"]);
    expect(directionsFromGamepad(pad({ axes: hatAxes(9 / 7) }), new Set(), hat)).toEqual([]);
  });

  it("accepts a distinctive hat value immediately and ignores trigger axes sitting at -1", () => {
    expect(directionsFromGamepad(pad({ axes: hatAxes(0.14286) }))).toEqual(["down"]);
    expect(directionsFromGamepad(pad({ mapping: "", axes: hatAxes(0.71429) }))).toEqual(["left"]);
    const triggers = Array.from({ length: 10 }, () => 0);
    triggers[4] = -1;
    triggers[5] = -1;
    expect(directionsFromGamepad(pad({ axes: triggers }))).toEqual([]);
    expect(directionsFromGamepad(pad({ axes: hatAxes(-1) }))).toEqual([]);
  });

  it("treats a half-pressed or numeric button as held and ignores a non-standard stick", () => {
    const gamepad = press(pad(), DPAD_DOWN, 0.5);
    expect(directionsFromGamepad(gamepad)).toEqual(["down"]);
    const numeric = pad({
      buttons: Array.from({ length: 17 }, (_, index) => (index === DPAD_LEFT ? 1 : 0)) as unknown as GamepadButton[],
    });
    expect(directionsFromGamepad(numeric)).toEqual(["left"]);
    expect(directionsFromGamepad(pad({ mapping: "", axes: [1, 1, 0, 0] }))).toEqual([]);
    expect(directionsFromGamepad(pad({ axes: [Number.NaN, 0, 0, 0] }))).toEqual([]);
  });

  it("reads a two-axis HID D-pad on axes 6 and 7", () => {
    const axes = [0, 0, 0, 0, 0, 0, -1, 1];
    expect(directionsFromGamepad(pad({ mapping: "", axes }))).toEqual(["down", "left"]);
  });

  it("reads the D-pad from a HID duplicate while the standard listing has dead buttons", () => {
    const standard = pad({ index: 0, axes: [0, 0, 0, 0] });
    const hid = pad({
      index: 1,
      id: "Xbox 360 Controller (Vendor: 045e Product: 028e)",
      mapping: "",
      axes: hatAxes(1 / 7),
    });
    expect(directionsFromGamepad(standard)).toEqual([]);
    expect(directionsFromGamepads([standard, hid], new Set(), new Map())).toEqual(["down"]);
  });

  it("reads Menu and A from a HID duplicate when the standard listing's buttons are dead", () => {
    const standard = pad({ index: 0 });
    const hid = press(pad({ index: 1, mapping: "" }), FACE_A);
    expect(padActionsPressed([standard, hid])).toMatchObject({ a: true, menu: false });
    expect(padActionsPressed([press(standard, BUTTON_MENU), hid]).menu).toBe(true);
  });
});

describe("arm axes", () => {
  function hold(): ArmHold {
    return { joint: null, retract: false, extend: false, negativeRest: new Set(), centered: new Set() };
  }

  it("maps the right stick to shoulder and elbow, with up as elbow positive", () => {
    const state = hold();
    expect(armFromGamepad(pad({ axes: [0, 0, 1, 0] }), state).joint).toEqual({ axis: "shoulder", direction: 1 });
    expect(armFromGamepad(pad({ axes: [0, 0, -1, 0] }), hold()).joint).toEqual({ axis: "shoulder", direction: -1 });
    expect(armFromGamepad(pad({ axes: [0, 0, 0, -1] }), hold()).joint).toEqual({ axis: "elbow", direction: 1 });
    expect(armFromGamepad(pad({ axes: [0, 0, 0, 1] }), hold()).joint).toEqual({ axis: "elbow", direction: -1 });
    expect(state.joint).toBe("shoulder");
  });

  it("keeps the joint already held when the stick is nearly diagonal", () => {
    const state = hold();
    armFromGamepad(pad({ axes: [0, 0, 0.8, 0] }), state);
    expect(armFromGamepad(pad({ axes: [0, 0, 0.7, -0.75] }), state).joint?.axis).toBe("shoulder");
    expect(armFromGamepad(pad({ axes: [0, 0, 0.4, -1] }), state).joint).toEqual({ axis: "elbow", direction: 1 });
  });

  it("ignores a resting right stick and an unmapped listing", () => {
    expect(armFromGamepad(pad({ axes: [0, 0, 0.2, -0.2] }), hold())).toEqual({ joint: null, y: 0 });
    expect(armFromGamepad(pad({ mapping: "", axes: [0, 0, 1, -1] }), hold())).toEqual({ joint: null, y: 0 });
  });

  it("extends on the right trigger, retracts on the left, and cancels when both are pulled", () => {
    expect(armFromGamepad(press(pad(), TRIGGER_RIGHT), hold()).y).toBe(-1);
    expect(armFromGamepad(press(pad(), TRIGGER_LEFT, 0.8), hold()).y).toBe(1);
    const both = press(press(pad(), TRIGGER_LEFT), TRIGGER_RIGHT);
    expect(armFromGamepad(both, hold()).y).toBe(0);
  });

  it("treats a trigger axis resting at -1 as released and a full pull as extend", () => {
    const axes = [0, 0, 0, 0, -1, 1];
    expect(armFromGamepad(pad({ axes }), hold())).toEqual({
      joint: null,
      y: -1,
    });
    expect(armFromGamepad(pad({ axes: [0, 0, 0, 0, -1, -1] }), hold()).y).toBe(0);
  });

  it("counts a digital trigger whose value stays at 0", () => {
    const gamepad = pad();
    const buttons = Array.from(gamepad.buttons);
    buttons[TRIGGER_RIGHT] = { pressed: true, touched: true, value: 0 };
    expect(armFromGamepad(pad({ buttons }), hold()).y).toBe(-1);
  });

  it("reads triggers from the HID duplicate when the standard listing's triggers are dead", () => {
    const state = hold();
    const standard = pad({ index: 0, axes: [0, 0, 1, 0] });
    const resting = pad({
      index: 1,
      mapping: "",
      axes: [0, 0, 0, 0, -1, -1],
    });
    expect(armFromGamepads([standard, resting], 0, state)).toEqual({
      joint: { axis: "shoulder", direction: 1 },
      y: 0,
    });
    const pulled = pad({
      index: 1,
      mapping: "",
      axes: [0, 0, 0, 0, -1, 0],
    });
    expect(armFromGamepads([standard, pulled], 0, state)).toEqual({
      joint: { axis: "shoulder", direction: 1 },
      y: -1,
    });
  });

  it("does not turn a HID stick that rests at 0 into a trigger", () => {
    const state = hold();
    armFromGamepads([pad({ index: 1, mapping: "", axes: [0, 0, 0, 0] })], 1, state);
    expect(armFromGamepads([pad({ index: 1, mapping: "", axes: [0, 0, -1, 1] })], 1, state).y).toBe(0);
  });
});
