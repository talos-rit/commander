import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { errorResponse, makeRobot, makeSettings, makeStatus, mockApi } from "./test/fixtures";
import type { Status } from "./types";

function setup(initial: Status, routes: Record<string, unknown> = {}) {
  let current = initial;
  const api = mockApi({
    "GET /status": () => current,
    "POST /view": ({ body }: { body: unknown }) => {
      current = { ...current, view: { ...current.view, ...(body as object) } };
      return current;
    },
    "POST /cameras/select": ({ body }: { body: unknown }) => {
      const { slot, host } = body as { slot?: 1 | 2; host?: string };
      if (host) {
        current = { ...current, view: { ...current.view, selected_host: host } };
      } else if (slot) {
        const host = slot === 1 ? current.view.camera_1! : current.view.camera_2!;
        const two = current.view.display_mode === "two_screen";
        current = {
          ...current,
          view: {
            ...current.view,
            displayed_slot: slot,
            selected_host: host,
            displayed_hosts: two ? current.view.displayed_hosts : [host],
          },
        };
      }
      return current;
    },
    "POST /control/home": { host: "bluey.local" },
    "POST /control/auto-track": ({ body }: { body: unknown }) => {
      const { enabled, host } = body as { enabled: boolean; host: string };
      current = {
        ...current,
        connections: { ...current.connections, [host]: { ...current.connections[host], auto_tracking: enabled } },
      };
      return { enabled };
    },
    "POST /control/move/start": { ok: true },
    "POST /control/move/stop": { ok: true },
    "POST /control/jog-mode": { mode: "continuous" },
    "POST /control/model": { model: "yolo" },
    "POST /control/virtual-camera": ({ body }: { body: unknown }) => {
      const { enabled } = body as { enabled: boolean };
      current = { ...current, virtual_camera: enabled };
      return { enabled };
    },
    "GET /settings": makeSettings({ camera_1_host: "bluey.local" }),
    "GET /robots": { "bluey.local": makeRobot("bluey.local") },
    ...routes,
  });
  const user = userEvent.setup();
  render(<App />);
  return { ...api, user, update: (next: Status) => (current = next) };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("App with one camera", () => {
  it("shows the single feed with Home and Auto-Track and a disabled two-screen switch", async () => {
    setup(makeStatus());
    expect(await screen.findByTestId("pane-bluey.local")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /home/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /auto-track/i })).toHaveAttribute("aria-pressed", "false");
    const layout = screen.getByRole("radiogroup", { name: "Screen layout" });
    expect(within(layout).getByRole("radio", { name: /one screen/i })).toHaveAttribute("aria-checked", "true");
    expect(within(layout).getByRole("radio", { name: /two screen/i })).toBeDisabled();
    expect(layout.parentElement).toHaveAttribute("data-tooltip", expect.stringMatching(/needs two cameras/));
    expect(layout).toHaveAccessibleDescription(/pick a Camera 2 in Settings/);
    expect(screen.queryByRole("radiogroup", { name: "Camera shown" })).not.toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: "Camera switching" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Debug controls")).not.toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: "Interface mode" })).not.toBeInTheDocument();
  });

  it("toggles auto-track for the selected robot and reflects the state", async () => {
    const { user, callsTo } = setup(makeStatus());
    const track = await screen.findByRole("button", { name: /auto-track/i });
    await user.click(track);
    expect(callsTo("POST", "/control/auto-track")[0].body).toEqual({ enabled: true, host: "bluey.local" });
    await waitFor(() => expect(track).toHaveAttribute("aria-pressed", "true"));
    expect(within(track).getByText("On")).toBeInTheDocument();
    expect(screen.getByTestId("pane-bluey.local")).toHaveClass("pane--tracking");
    expect(screen.getByText("Tracking")).toBeInTheDocument();
  });

  it("sends Home to the selected robot", async () => {
    const { user, callsTo } = setup(makeStatus());
    await user.click(await screen.findByRole("button", { name: /home/i }));
    expect(callsTo("POST", "/control/home")[0].body).toEqual({ host: "bluey.local" });
    expect(screen.getByText("Homing…")).toBeInTheDocument();
  });

  it("toggles the virtual camera once the feed has a frame", async () => {
    const { user, callsTo } = setup(
      makeStatus({ connections: { "bluey.local": { has_video: true } } }),
    );
    const cam = await screen.findByRole("button", { name: /virtual cam/i });
    expect(cam).toHaveAttribute("aria-pressed", "false");
    await user.click(cam);
    expect(callsTo("POST", "/control/virtual-camera")[0].body).toEqual({ enabled: true });
    await waitFor(() => expect(cam).toHaveAttribute("aria-pressed", "true"));
    expect(within(cam).getByText("On")).toBeInTheDocument();
  });

  it("keeps the virtual camera off until a frame arrives", async () => {
    setup(makeStatus());
    expect(await screen.findByRole("button", { name: /virtual cam/i })).toBeDisabled();
  });

  it("disables Auto-Track for manual-only robots", async () => {
    setup(makeStatus({ connections: { "bluey.local": { manual_only: true } } }));
    const track = await screen.findByRole("button", { name: /auto-track/i });
    expect(track).toBeDisabled();
    expect(within(track).getByText("Manual only")).toBeInTheDocument();
  });

  it("shows offline chips when the robot and video are down", async () => {
    setup(makeStatus({ connections: { "bluey.local": { operator_connected: false, open: false } } }));
    expect(await screen.findByText("Robot offline")).toBeInTheDocument();
    expect(screen.getByText("No video")).toBeInTheDocument();
    expect(screen.getByText("Not connected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /home/i })).toBeDisabled();
  });

  it("surfaces API errors as a dismissible toast", async () => {
    const { user } = setup(makeStatus(), {
      "POST /control/auto-track": () => errorResponse(409, "Robot is busy"),
    });
    await user.click(await screen.findByRole("button", { name: /auto-track/i }));
    const toast = await screen.findByText("Robot is busy");
    await user.click(within(toast.parentElement!).getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText("Robot is busy")).not.toBeInTheDocument();
  });
});

describe("App with no cameras", () => {
  it("shows the empty state and opens settings", async () => {
    const { user } = setup(makeStatus({ hosts: [] }), {
      "GET /robots": {},
      "GET /settings": makeSettings(),
    });
    expect(await screen.findByText("No camera assigned")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /auto-track/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open settings" }));
    expect(await screen.findByRole("dialog", { name: "Settings" })).toBeInTheDocument();
    expect(await screen.findByRole("form", { name: "Add robot" })).toBeInTheDocument();
  });
});

describe("App with two cameras", () => {
  const hosts = ["bluey.local", "raspberrypi.local"];

  it("switches the shown camera in one-screen manual mode", async () => {
    const { user, callsTo } = setup(makeStatus({ hosts }));
    expect(await screen.findByRole("radiogroup", { name: "Screen layout" })).toBeInTheDocument();
    expect(screen.getByTestId("pane-bluey.local")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Cam 2" }));
    expect(callsTo("POST", "/cameras/select")[0].body).toEqual({ slot: 2 });
    expect(await screen.findByTestId("pane-raspberrypi.local")).toBeInTheDocument();
    expect(screen.queryByTestId("pane-bluey.local")).not.toBeInTheDocument();
  });

  it("shows both feeds side by side in two-screen mode and selects a pane", async () => {
    const { user, callsTo } = setup(makeStatus({ hosts, view: { display_mode: "two_screen" } }));
    expect(await screen.findByTestId("pane-bluey.local")).toBeInTheDocument();
    expect(screen.getByTestId("pane-raspberrypi.local")).toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: "Camera switching" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /control camera 2/i }));
    expect(callsTo("POST", "/cameras/select")[0].body).toEqual({ host: "raspberrypi.local" });
    await waitFor(() => expect(screen.getByTestId("pane-raspberrypi.local")).toHaveClass("pane--selected"));
  });

  it("changes layout and switching mode through the rocker switches", async () => {
    const { user, callsTo } = setup(makeStatus({ hosts }));
    await user.click(await screen.findByRole("radio", { name: /dynamic/i }));
    expect(callsTo("POST", "/view")[0].body).toEqual({ one_screen_mode: "dynamic" });
    expect(await screen.findByText(/auto-switch coming soon/)).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /two screen/i }));
    expect(callsTo("POST", "/view")[1].body).toEqual({ display_mode: "two_screen" });
  });

  it("flips the layout by clicking the switch track", async () => {
    const { user, callsTo } = setup(makeStatus({ hosts }));
    const layout = await screen.findByRole("radiogroup", { name: "Screen layout" });
    await user.click(layout.querySelector(".rocker__track")!);
    expect(callsTo("POST", "/view")[0].body).toEqual({ display_mode: "two_screen" });
    await waitFor(() => expect(layout).toHaveAttribute("data-side", "right"));
  });

  it("uses number keys to pick the camera", async () => {
    const { callsTo } = setup(makeStatus({ hosts }));
    await screen.findByTestId("pane-bluey.local");
    fireEvent.keyDown(window, { key: "2" });
    await waitFor(() => expect(callsTo("POST", "/cameras/select")[0]?.body).toEqual({ slot: 2 }));
  });
});

describe("Debug mode", () => {
  it("adds the jog pad, model slider and telemetry", async () => {
    const { user, callsTo } = setup(
      makeStatus({
        view: { ui_mode: "debug" },
        connections: {
          "bluey.local": {
            telemetry: { joint_counts: [10, 20], joint_age_s: 0.2, encoder_counts: null, encoder_age_s: null },
          },
        },
      }),
    );
    const rail = await screen.findByLabelText("Debug controls");
    expect(within(rail).getByRole("button", { name: "Jog up" })).toBeEnabled();
    expect(within(rail).getByText("Hold a button or an arrow key.")).toBeInTheDocument();
    expect(within(rail).queryByText(/controller/i)).not.toBeInTheDocument();
    expect(within(rail).getByText("10 20")).toBeInTheDocument();
    expect(within(rail).getByText("200 ms ago")).toBeInTheDocument();
    expect(within(rail).getByText("never")).toBeInTheDocument();

    await user.click(within(rail).getByRole("button", { name: "Use Medium" }));
    expect(callsTo("POST", "/control/model")[0].body).toEqual({ model: "yolo_medium" });
    await user.click(within(rail).getByRole("radio", { name: "Continuous" }));
    expect(callsTo("POST", "/control/jog-mode")[0].body).toEqual({ mode: "continuous" });
  });

  it("shows the saved default size while no model is loaded", async () => {
    const status = makeStatus({ view: { ui_mode: "debug" } });
    setup({ ...status, tracking: { ...status.tracking, default_model: "yolo_medium" } });
    const slider = await screen.findByRole("slider", { name: "Detection model" });
    expect(slider).toHaveAttribute("aria-valuetext", "Medium (yolo_medium)");
    expect(screen.getByText("not loaded")).toBeInTheDocument();
  });

  it("only loads a model once the slider is released", async () => {
    const { callsTo } = setup(makeStatus({ view: { ui_mode: "debug" } }));
    const slider = await screen.findByRole("slider", { name: "Detection model" });
    fireEvent.change(slider, { target: { value: "1" } });
    fireEvent.change(slider, { target: { value: "3" } });
    expect(slider).toHaveAttribute("aria-valuetext", "Large (yolo_large)");
    expect(callsTo("POST", "/control/model")).toHaveLength(0);
    fireEvent.pointerUp(slider);
    await waitFor(() => expect(callsTo("POST", "/control/model")).toHaveLength(1));
    expect(callsTo("POST", "/control/model")[0].body).toEqual({ model: "yolo_large" });
  });

  it("unloads the model", async () => {
    const status = makeStatus({ view: { ui_mode: "debug" } });
    const { user, callsTo } = setup({ ...status, tracking: { ...status.tracking, model: "yolo_small" } });
    await user.click(await screen.findByRole("button", { name: "Unload" }));
    expect(callsTo("POST", "/control/model")[0].body).toEqual({ model: null });
  });

  it("leaves debug mode from the top bar chip", async () => {
    const { user, callsTo } = setup(makeStatus({ view: { ui_mode: "debug" } }));
    await user.click(await screen.findByRole("button", { name: /debug/i }));
    expect(callsTo("POST", "/view")[0].body).toEqual({ ui_mode: "simple" });
    await waitFor(() => expect(screen.queryByLabelText("Debug controls")).not.toBeInTheDocument());
  });

  it("explains how to install YOLO when no model is available", async () => {
    const status = makeStatus({ view: { ui_mode: "debug" } });
    setup({ ...status, tracking: { ...status.tracking, model_options: ["basic"] } });
    expect(await screen.findByText(/uv sync --extra yolo/)).toBeInTheDocument();
  });

  it("starts and stops jogging on pointer press and release", async () => {
    const { callsTo } = setup(makeStatus({ view: { ui_mode: "debug" } }));
    const up = await screen.findByRole("button", { name: "Jog up" });
    fireEvent.pointerDown(up, { pointerId: 1 });
    fireEvent.pointerDown(up, { pointerId: 1 });
    fireEvent.pointerUp(up, { pointerId: 1 });
    fireEvent.pointerUp(up, { pointerId: 1 });
    await waitFor(() => expect(callsTo("POST", "/control/move/stop")).toHaveLength(1));
    expect(callsTo("POST", "/control/move/start")).toHaveLength(1);
    expect(callsTo("POST", "/control/move/start")[0].body).toEqual({ direction: "up" });
  });

  it("jogs with the arrow keys and ignores repeats", async () => {
    const { callsTo } = setup(makeStatus({ view: { ui_mode: "debug" } }));
    await screen.findByLabelText("Debug controls");
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    fireEvent.keyDown(window, { key: "ArrowLeft", repeat: true });
    fireEvent.keyUp(window, { key: "ArrowLeft" });
    await waitFor(() => expect(callsTo("POST", "/control/move/stop")).toHaveLength(1));
    expect(callsTo("POST", "/control/move/start")).toEqual([
      { method: "POST", path: "/control/move/start", body: { direction: "left" } },
    ]);
  });

  it("releases held keys when the window loses focus", async () => {
    const { callsTo } = setup(makeStatus({ view: { ui_mode: "debug" } }));
    await screen.findByLabelText("Debug controls");
    fireEvent.keyDown(window, { key: "ArrowUp" });
    fireEvent.blur(window);
    await waitFor(() => expect(callsTo("POST", "/control/move/stop")[0]?.body).toEqual({ direction: "up" }));
  });

  it("disables the jog pad while auto-tracking", async () => {
    setup(makeStatus({ view: { ui_mode: "debug" }, connections: { "bluey.local": { auto_tracking: true } } }));
    expect(await screen.findByRole("button", { name: "Jog up" })).toBeDisabled();
    expect(screen.getByText("Turn off Auto-Track to jog manually.")).toBeInTheDocument();
  });

  it("does not jog with arrows in simple mode", async () => {
    const { calls } = setup(makeStatus());
    await screen.findByTestId("pane-bluey.local");
    fireEvent.keyDown(window, { key: "ArrowUp" });
    expect(calls.some((c) => c.path === "/control/move/start")).toBe(false);
  });
});

describe("Controller", () => {
  const frames: FrameRequestCallback[] = [];
  let pads: (Gamepad | null)[] = [];

  function fakePad(overrides: Partial<Gamepad> = {}): Gamepad {
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

  function press(gamepad: Gamepad, index: number) {
    const buttons = Array.from(gamepad.buttons);
    buttons[index] = { pressed: true, touched: true, value: 1 };
    return fakePad({ ...gamepad, buttons });
  }

  async function step() {
    const pending = frames.splice(0, frames.length);
    expect(pending.length).toBeGreaterThan(0);
    await act(async () => {
      pending.forEach((cb) => cb(0));
    });
  }

  beforeEach(() => {
    pads = [null, null, null, null];
    frames.length = 0;
    Object.defineProperty(navigator, "getGamepads", { configurable: true, value: () => pads });
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      frames.push(cb);
      return frames.length;
    });
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
  });

  afterEach(() => {
    Reflect.deleteProperty(navigator, "getGamepads");
  });

  it("jogs the selected robot from the left stick and releases inside the dead zone", async () => {
    const { callsTo } = setup(makeStatus({ view: { ui_mode: "debug" } }));
    await screen.findByLabelText("Debug controls");
    pads[0] = fakePad({ axes: [0, -1, 0, 0] });
    await step();
    await waitFor(() => expect(callsTo("POST", "/control/move/start")).toHaveLength(1));
    expect(callsTo("POST", "/control/move/start")[0].body).toEqual({ direction: "up" });
    expect(screen.getByRole("button", { name: "Jog up" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTitle(/Left stick and D-pad/)).toHaveClass("chip--ok");
    expect(screen.getByText("Xbox 360 Controller")).toBeInTheDocument();
    expect(screen.getByText(/Right stick moves the shoulder/)).toBeInTheDocument();

    await step();
    expect(callsTo("POST", "/control/move/start")).toHaveLength(1);

    pads[0] = fakePad({ axes: [-1, 1, 0, 0] });
    await step();
    await waitFor(() => expect(callsTo("POST", "/control/move/start")).toHaveLength(3));
    const moves = callsTo("POST", "/control/move/start").map((call) => call.body);
    expect(moves).toEqual([{ direction: "up" }, { direction: "down" }, { direction: "left" }]);
    expect(callsTo("POST", "/control/move/stop").map((call) => call.body)).toEqual([{ direction: "up" }]);

    pads[0] = fakePad();
    await step();
    await waitFor(() => expect(callsTo("POST", "/control/move/stop")).toHaveLength(3));
  });

  it("jogs the shoulder and elbow from the right stick and extends from the trigger", async () => {
    const { callsTo } = setup(makeStatus({ view: { ui_mode: "debug" } }));
    await screen.findByLabelText("Debug controls");
    pads[0] = fakePad({ axes: [0, 0, 1, 0] });
    await step();
    await waitFor(() => expect(callsTo("POST", "/control/joint/start")).toHaveLength(1));
    expect(callsTo("POST", "/control/joint/start")[0].body).toEqual({ axis: "shoulder", direction: 1 });
    expect(callsTo("POST", "/control/move/start")).toHaveLength(0);

    pads[0] = fakePad({ axes: [0, 0, 0, -1] });
    await step();
    await waitFor(() => expect(callsTo("POST", "/control/joint/start")).toHaveLength(2));
    expect(callsTo("POST", "/control/joint/start")[1].body).toEqual({ axis: "elbow", direction: 1 });

    pads[0] = press(fakePad(), 7);
    await step();
    await waitFor(() => expect(callsTo("POST", "/control/joint/stop")).toHaveLength(1));
    await waitFor(() => expect(callsTo("POST", "/control/cartesian/start")).toHaveLength(1));
    expect(callsTo("POST", "/control/cartesian/start")[0].body).toEqual({ x: 0, y: -1, z: 0 });

    pads[0] = fakePad();
    await step();
    await waitFor(() => expect(callsTo("POST", "/control/cartesian/stop")).toHaveLength(1));
  });

  it("extends from a HID duplicate when the standard listing's triggers stay dead", async () => {
    const { callsTo } = setup(makeStatus({ view: { ui_mode: "debug" } }));
    await screen.findByLabelText("Debug controls");
    pads[0] = fakePad({ axes: [0, 0, 0, 0] });
    pads[1] = fakePad({
      index: 1,
      id: "Xbox 360 Controller (Vendor: 045e Product: 028e)",
      mapping: "",
      axes: [0, 0, 0, 0, -1, 1],
    });
    await step();
    await waitFor(() => expect(callsTo("POST", "/control/cartesian/start")).toHaveLength(1));
    expect(callsTo("POST", "/control/cartesian/start")[0].body).toEqual({ x: 0, y: -1, z: 0 });
    expect(callsTo("POST", "/control/move/start")).toHaveLength(0);
  });

  it("keeps jogging while either the stick or an arrow key is still held", async () => {
    const { callsTo } = setup(makeStatus({ view: { ui_mode: "debug" } }));
    await screen.findByLabelText("Debug controls");
    pads[0] = fakePad({ axes: [0, -1, 0, 0] });
    await step();
    fireEvent.keyDown(window, { key: "ArrowUp" });
    fireEvent.keyUp(window, { key: "ArrowUp" });
    expect(callsTo("POST", "/control/move/stop")).toHaveLength(0);
    expect(callsTo("POST", "/control/move/start")).toHaveLength(1);

    pads[0] = fakePad();
    await step();
    await waitFor(() => expect(callsTo("POST", "/control/move/stop")).toHaveLength(1));
  });

  function hatAxes(value: number): number[] {
    const axes = Array.from({ length: 10 }, () => 0);
    axes[9] = value;
    return axes;
  }

  it("jogs from a hat-switch D-pad when the D-pad buttons never report pressed", async () => {
    const { callsTo } = setup(makeStatus({ view: { ui_mode: "debug" } }));
    await screen.findByLabelText("Debug controls");
    pads[0] = fakePad({ axes: hatAxes(9 / 7) });
    await step();
    expect(callsTo("POST", "/control/move/start")).toHaveLength(0);

    pads[0] = fakePad({ axes: hatAxes(-1) });
    await step();
    await waitFor(() => expect(callsTo("POST", "/control/move/start")[0]?.body).toEqual({ direction: "up" }));
    expect(screen.getByRole("button", { name: "Jog up" })).toHaveAttribute("aria-pressed", "true");

    pads[0] = fakePad({ axes: hatAxes(9 / 7) });
    await step();
    await waitFor(() => expect(callsTo("POST", "/control/move/stop")[0]?.body).toEqual({ direction: "up" }));
  });

  it("jogs an unrecognized controller from its hat-switch D-pad", async () => {
    const { callsTo } = setup(makeStatus({ view: { ui_mode: "debug" } }));
    await screen.findByLabelText("Debug controls");
    pads[0] = fakePad({ id: "Weird Stick (Vendor: 0000)", mapping: "", axes: hatAxes(1 / 7) });
    await step();
    await waitFor(() => expect(callsTo("POST", "/control/move/start")[0]?.body).toEqual({ direction: "down" }));
  });

  it("jogs from a HID duplicate when the standard listing's D-pad buttons never fire", async () => {
    const { callsTo } = setup(makeStatus({ view: { ui_mode: "debug" } }));
    await screen.findByLabelText("Debug controls");
    pads[0] = fakePad({ axes: [0, 0, 0, 0] });
    pads[1] = fakePad({
      index: 1,
      id: "Xbox 360 Controller (Vendor: 045e Product: 028e)",
      mapping: "",
      axes: hatAxes(1 / 7),
    });
    await step();
    await waitFor(() => expect(callsTo("POST", "/control/move/start")[0]?.body).toEqual({ direction: "down" }));
  });

  it("jogs from the D-pad", async () => {
    const { callsTo } = setup(makeStatus({ view: { ui_mode: "debug" } }));
    await screen.findByLabelText("Debug controls");
    pads[0] = press(fakePad(), 15);
    await step();
    await waitFor(() => expect(callsTo("POST", "/control/move/start")[0]?.body).toEqual({ direction: "right" }));
  });

  it("does not jog outside debug mode, but shows that the controller is connected", async () => {
    const { calls } = setup(makeStatus());
    await screen.findByTestId("pane-bluey.local");
    pads[0] = fakePad({ axes: [0, -1, 0, 0] });
    await step();
    expect(calls.some((call) => call.path === "/control/move/start")).toBe(false);
    expect(screen.getByTitle(/Menu toggles Debug mode/)).toHaveClass("chip--warn");
  });

  it("does not jog while auto-tracking", async () => {
    const { calls } = setup(
      makeStatus({ view: { ui_mode: "debug" }, connections: { "bluey.local": { auto_tracking: true } } }),
    );
    await screen.findByLabelText("Debug controls");
    pads[0] = fakePad({ axes: [1, 0, 0, 0] });
    await step();
    expect(calls.some((call) => call.path === "/control/move/start")).toBe(false);
    expect(screen.getByTitle(/Turn off Auto-Track/)).toBeInTheDocument();
  });

  it("does not jog while the selected robot is offline", async () => {
    const { calls } = setup(
      makeStatus({ view: { ui_mode: "debug" }, connections: { "bluey.local": { open: false } } }),
    );
    await screen.findByLabelText("Debug controls");
    pads[0] = fakePad({ axes: [1, 0, 0, 0] });
    await step();
    expect(calls.some((call) => call.path === "/control/move/start")).toBe(false);
    expect(screen.getByTitle(/isn't ready/)).toBeInTheDocument();
  });

  it("stops jogging when the window loses focus, settings open, or the pad disconnects", async () => {
    const { user, callsTo } = setup(makeStatus({ view: { ui_mode: "debug" } }));
    await screen.findByLabelText("Debug controls");
    pads[0] = fakePad({ axes: [0, -1, 0, 0] });
    await step();
    await waitFor(() => expect(callsTo("POST", "/control/move/start")).toHaveLength(1));

    fireEvent.blur(window);
    await waitFor(() => expect(callsTo("POST", "/control/move/stop")[0]?.body).toEqual({ direction: "up" }));
    fireEvent.focus(window);
    await step();
    expect(callsTo("POST", "/control/move/start")).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "Settings" }));
    await screen.findByRole("dialog", { name: "Settings" });
    await waitFor(() => expect(callsTo("POST", "/control/move/stop")).toHaveLength(2));
    await step();
    expect(callsTo("POST", "/control/move/start")).toHaveLength(2);
    expect(screen.getByTitle(/Close Settings/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Close settings" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await step();
    await waitFor(() => expect(callsTo("POST", "/control/move/start")).toHaveLength(3));

    const disconnected = fakePad();
    pads[0] = null;
    window.dispatchEvent(Object.assign(new Event("gamepaddisconnected"), { gamepad: disconnected }));
    await waitFor(() => expect(callsTo("POST", "/control/move/stop")).toHaveLength(3));
    await step();
    expect(screen.queryByText("Xbox 360 Controller")).not.toBeInTheDocument();
  });

  it("ignores a controller that does not use the standard layout", async () => {
    const { calls } = setup(makeStatus({ view: { ui_mode: "debug" } }));
    await screen.findByLabelText("Debug controls");
    pads[0] = fakePad({ id: "Weird Stick (Vendor: 0000)", mapping: "", axes: [1, 1, 0, 0] });
    await step();
    expect(calls.some((call) => call.path === "/control/move/start")).toBe(false);
    expect(screen.getByText("Weird Stick")).toBeInTheDocument();
    expect(screen.getByTitle(/standard Xbox layout/)).toHaveClass("chip--warn");
  });

  it("switches cameras from the shoulder buttons, once per press", async () => {
    const hosts = ["bluey.local", "raspberrypi.local"];
    const { callsTo } = setup(makeStatus({ hosts }));
    await screen.findByTestId("pane-bluey.local");
    let gamepad = press(fakePad(), 5);
    pads[0] = gamepad;
    await step();
    await step();
    await waitFor(() => expect(callsTo("POST", "/cameras/select")).toHaveLength(1));
    expect(callsTo("POST", "/cameras/select")[0].body).toEqual({ slot: 2 });

    gamepad = fakePad();
    pads[0] = gamepad;
    await step();
    gamepad = press(gamepad, 4);
    pads[0] = gamepad;
    await step();
    await waitFor(() => expect(callsTo("POST", "/cameras/select")).toHaveLength(2));
    expect(callsTo("POST", "/cameras/select")[1].body).toEqual({ slot: 1 });
  });

  it("rolls the shoulder buttons past either end", async () => {
    const hosts = ["bluey.local", "raspberrypi.local"];
    const { callsTo } = setup(makeStatus({ hosts }));
    await screen.findByTestId("pane-bluey.local");

    pads[0] = press(fakePad(), 5);
    await step();
    await waitFor(() => expect(callsTo("POST", "/cameras/select")).toHaveLength(1));
    expect(callsTo("POST", "/cameras/select")[0].body).toEqual({ slot: 2 });

    pads[0] = fakePad();
    await step();
    pads[0] = press(fakePad(), 5);
    await step();
    await waitFor(() => expect(callsTo("POST", "/cameras/select")).toHaveLength(2));
    expect(callsTo("POST", "/cameras/select")[1].body).toEqual({ slot: 1 });

    pads[0] = fakePad();
    await step();
    pads[0] = press(fakePad(), 4);
    await step();
    await waitFor(() => expect(callsTo("POST", "/cameras/select")).toHaveLength(3));
    expect(callsTo("POST", "/cameras/select")[2].body).toEqual({ slot: 2 });
  });

  it("binds Menu, Back, and the face buttons", async () => {
    const hosts = ["bluey.local", "raspberrypi.local"];
    const { callsTo } = setup(
      makeStatus({ hosts, connections: { "bluey.local": { has_video: true } } }),
    );
    await screen.findByTestId("pane-bluey.local");

    pads[0] = press(fakePad(), 9);
    await step();
    await waitFor(() => expect(callsTo("POST", "/view")[0]?.body).toEqual({ ui_mode: "debug" }));
    pads[0] = fakePad();
    await step();
    pads[0] = press(fakePad(), 9);
    await step();
    await waitFor(() => expect(callsTo("POST", "/view")[1]?.body).toEqual({ ui_mode: "simple" }));

    pads[0] = fakePad();
    await step();
    pads[0] = press(fakePad(), 8);
    await step();
    await step();
    await waitFor(() => expect(callsTo("POST", "/control/home")).toHaveLength(1));
    expect(callsTo("POST", "/control/home")[0].body).toEqual({ host: "bluey.local" });

    pads[0] = fakePad();
    await step();
    pads[0] = press(fakePad(), 0);
    await step();
    await waitFor(() => expect(callsTo("POST", "/control/auto-track")[0]?.body).toEqual({ enabled: true, host: "bluey.local" }));
    await step();
    expect(callsTo("POST", "/control/auto-track")).toHaveLength(1);

    pads[0] = fakePad();
    await step();
    pads[0] = press(fakePad(), 3);
    await step();
    await waitFor(() => expect(callsTo("POST", "/view").some((call) => (call.body as { one_screen_mode?: string }).one_screen_mode === "dynamic")).toBe(true));

    pads[0] = fakePad();
    await step();
    pads[0] = press(fakePad(), 2);
    await step();
    await waitFor(() => expect(callsTo("POST", "/control/virtual-camera")[0]?.body).toEqual({ enabled: true }));

    pads[0] = fakePad();
    await step();
    pads[0] = press(fakePad(), 1);
    await step();
    await waitFor(() => expect(callsTo("POST", "/view").some((call) => (call.body as { display_mode?: string }).display_mode === "two_screen")).toBe(true));
    pads[0] = fakePad();
    await step();
    pads[0] = press(fakePad(), 1);
    await step();
    await waitFor(() => expect(callsTo("POST", "/view").some((call) => (call.body as { display_mode?: string }).display_mode === "one_screen")).toBe(true));
  });

  it("does not change the layout from B when only one camera is assigned", async () => {
    const { calls } = setup(makeStatus());
    await screen.findByTestId("pane-bluey.local");
    pads[0] = press(fakePad(), 1);
    await step();
    expect(calls.some((call) => call.path === "/view")).toBe(false);
  });

  it("does not start the virtual camera before a frame arrives", async () => {
    const { calls } = setup(makeStatus());
    await screen.findByTestId("pane-bluey.local");
    pads[0] = press(fakePad(), 2);
    await step();
    expect(calls.some((call) => call.path === "/control/virtual-camera")).toBe(false);
  });

  it("ignores face buttons while Settings is open", async () => {
    const { user, calls } = setup(makeStatus());
    await user.click(await screen.findByRole("button", { name: "Settings" }));
    pads[0] = press(fakePad(), 0);
    await step();
    expect(calls.some((call) => call.path === "/control/auto-track")).toBe(false);
  });

  it("does not switch cameras in dynamic mode", async () => {
    const hosts = ["bluey.local", "raspberrypi.local"];
    const { calls } = setup(makeStatus({ hosts, view: { one_screen_mode: "dynamic" } }));
    await screen.findByText(/auto-switch coming soon/);
    pads[0] = press(fakePad(), 5);
    await step();
    expect(calls.some((call) => call.path === "/cameras/select")).toBe(false);
  });
});

describe("Keyboard shortcuts", () => {
  it("homes with H and toggles tracking with T", async () => {
    const { callsTo } = setup(makeStatus());
    await screen.findByTestId("pane-bluey.local");
    fireEvent.keyDown(window, { key: "h" });
    fireEvent.keyDown(window, { key: "T" });
    await waitFor(() => expect(callsTo("POST", "/control/auto-track")).toHaveLength(1));
    expect(callsTo("POST", "/control/home")).toHaveLength(1);
  });

  it("ignores shortcuts while typing or with the settings open", async () => {
    const { user, calls } = setup(makeStatus());
    await user.click(await screen.findByRole("button", { name: "Settings" }));
    await screen.findByRole("dialog");
    fireEvent.keyDown(window, { key: "h" });
    const input = await screen.findByLabelText("Web host");
    fireEvent.keyDown(input, { key: "t" });
    expect(calls.some((c) => c.path.startsWith("/control"))).toBe(false);
  });
});

describe("Backend connection", () => {
  it("shows a loading message and then an offline banner", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("offline"))));
    render(<App />);
    expect((await screen.findAllByText("Commander backend is unreachable")).length).toBeGreaterThan(0);
  });

  it("shows a connecting state while the backend opens cameras, then the feed", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let starting = true;
    const starting503 = () =>
      new Response(JSON.stringify({ detail: "Commander is connecting to cameras…", starting: true }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      });
    setup(makeStatus(), { "GET /status": () => (starting ? starting503() : makeStatus()) });

    expect(await screen.findByText("Connecting to cameras…")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Settings" })).not.toBeInTheDocument();

    starting = false;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(await screen.findByTestId("pane-bluey.local")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Settings" })).toBeInTheDocument();
  });

  it("keeps polling status", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { callsTo } = setup(makeStatus());
    await screen.findByTestId("pane-bluey.local");
    const before = callsTo("GET", "/status").length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(callsTo("GET", "/status").length).toBeGreaterThan(before);
  });
});
