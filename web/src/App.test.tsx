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
