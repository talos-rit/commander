import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { errorResponse, makeRobot, makeSettings, mockApi } from "../test/fixtures";
import type { AppSettings, RobotConfig } from "../types";
import { SettingsPanel } from "./SettingsPanel";

function setup({
  robots = { "bluey.local": makeRobot("bluey.local") } as Record<string, RobotConfig>,
  settings = makeSettings({ camera_1_host: "bluey.local" }),
  routes = {} as Record<string, unknown>,
} = {}) {
  let currentRobots = { ...robots };
  let currentSettings: AppSettings = settings;
  const api = mockApi({
    "GET /settings": () => currentSettings,
    "PUT /settings": ({ body }: { body: unknown }) => (currentSettings = { ...currentSettings, ...(body as object) }),
    "GET /robots": () => currentRobots,
    "POST /robots": ({ body }: { body: unknown }) => {
      const robot = makeRobot((body as RobotConfig).socket_host, body as RobotConfig);
      currentRobots = { ...currentRobots, [robot.socket_host]: robot };
      return robot;
    },
    ...Object.fromEntries(
      Object.keys(robots).flatMap((host) => [
        [
          `PUT /robots/${host}`,
          ({ body }: { body: unknown }) => {
            currentRobots = { ...currentRobots, [host]: { ...currentRobots[host], ...(body as object) } };
            return currentRobots[host];
          },
        ],
        [
          `DELETE /robots/${host}`,
          () => {
            const { [host]: _removed, ...rest } = currentRobots;
            currentRobots = rest;
            return undefined;
          },
        ],
      ]),
    ),
    ...routes,
  });
  const onClose = vi.fn();
  const onChanged = vi.fn();
  const user = userEvent.setup();
  const view = render(
    <SettingsPanel open modelOptions={["basic", "yolo_nano", "yolo_small"]} onClose={onClose} onChanged={onChanged} />,
  );
  return { ...api, user, onClose, onChanged, view };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("SettingsPanel", () => {
  it("renders nothing when closed", () => {
    mockApi({});
    const { container } = render(<SettingsPanel open={false} modelOptions={[]} onClose={() => {}} onChanged={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("lists robots and the current camera slots", async () => {
    setup();
    expect(await screen.findByText("bluey.local", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByLabelText("Camera 1 (primary)")).toHaveValue("bluey.local");
    expect(screen.getByLabelText("Camera 2 (optional)")).toHaveValue("");
    expect(screen.queryByRole("form", { name: "Add robot" })).not.toBeInTheDocument();
  });

  it("adds a robot with a numeric device index", async () => {
    const { user, callsTo, onChanged } = setup();
    await user.click(await screen.findByRole("button", { name: /add robot/i }));
    const form = screen.getByRole("form", { name: "Add robot" });
    await user.type(within(form).getByLabelText("Operator host"), "raspberrypi.local");
    const camera = within(form).getByLabelText(/^camera$/i);
    await user.clear(camera);
    await user.type(camera, "0");
    await user.click(within(form).getByLabelText(/manual only/i));
    await user.click(within(form).getByRole("button", { name: /add robot/i }));
    await waitFor(() => expect(callsTo("POST", "/robots")).toHaveLength(1));
    expect(callsTo("POST", "/robots")[0].body).toEqual({
      socket_host: "raspberrypi.local",
      socket_port: 61616,
      camera_index: 0,
      fps: 30,
      manual_only: true,
      pi_vision_url: null,
    });
    expect(await screen.findByText("raspberrypi.local", { selector: "strong" })).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalled();
  });

  it("fills the camera URL from the operator host as it is typed", async () => {
    const { user, callsTo } = setup({ robots: {}, settings: makeSettings() });
    const form = await screen.findByRole("form", { name: "Add robot" });
    const host = within(form).getByLabelText("Operator host");
    const camera = within(form).getByLabelText(/^camera$/i);

    expect(camera).toHaveValue("");
    expect(within(form).getByText("Fills in from the operator host.")).toBeInTheDocument();

    await user.type(host, "blu");
    expect(camera).toHaveValue("rtsp://blu:8554/camera");
    await user.type(host, "ey.local");
    expect(camera).toHaveValue("rtsp://bluey.local:8554/camera");
    expect(within(form).getByText("Follows the operator host.")).toBeInTheDocument();

    await user.click(within(form).getByRole("button", { name: /add robot/i }));
    await waitFor(() => expect(callsTo("POST", "/robots")).toHaveLength(1));
    expect(callsTo("POST", "/robots")[0].body).toMatchObject({
      socket_host: "bluey.local",
      socket_port: 61616,
      camera_index: "rtsp://bluey.local:8554/camera",
      fps: 30,
      manual_only: false,
    });
  });

  it("keeps a camera URL the user edited, and follows again after it is cleared", async () => {
    const { user } = setup({ robots: {}, settings: makeSettings() });
    const form = await screen.findByRole("form", { name: "Add robot" });
    const host = within(form).getByLabelText("Operator host");
    const camera = within(form).getByLabelText(/^camera$/i);

    await user.type(host, "bluey.local");
    await user.clear(camera);
    await user.type(camera, "0");
    await user.type(host, "x");
    expect(camera).toHaveValue("0");
    expect(within(form).getByText("RTSP or HTTP URL, or a device index.")).toBeInTheDocument();

    await user.clear(camera);
    await user.type(host, "y");
    expect(camera).toHaveValue("rtsp://bluey.localxy:8554/camera");
  });

  it("shows Connecting… while a new robot connection is opening", async () => {
    let release: (robot: RobotConfig) => void = () => {};
    const gate = new Promise<RobotConfig>((resolve) => {
      release = resolve;
    });
    const { user } = setup({
      robots: {},
      settings: makeSettings(),
      routes: { "POST /robots": () => gate },
    });
    const form = await screen.findByRole("form", { name: "Add robot" });
    await user.type(within(form).getByLabelText("Operator host"), "bluey.local");
    const submitted = user.click(within(form).getByRole("button", { name: /add robot/i }));
    const connecting = await screen.findByRole("button", { name: /connecting/i });
    expect(connecting).toBeDisabled();
    expect(connecting).toHaveAttribute("aria-busy", "true");
    expect(within(form).getByLabelText("Operator host")).toBeDisabled();
    release(makeRobot("bluey.local"));
    await submitted;
    expect(await screen.findByRole("button", { name: /add robot/i })).toBeEnabled();
    expect(screen.queryByRole("button", { name: /connecting/i })).not.toBeInTheDocument();
  });

  it("opens the add form straight away when there are no robots", async () => {
    setup({ robots: {}, settings: makeSettings() });
    expect(await screen.findByRole("form", { name: "Add robot" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Camera 2 (optional)")).toBeDisabled();
  });

  it("shows validation errors from the backend", async () => {
    const { user, callsTo } = setup({
      routes: { "POST /robots": () => errorResponse(422, [{ msg: "Invalid port" }, { msg: "Bad camera" }]) },
    });
    await user.click(await screen.findByRole("button", { name: /add robot/i }));
    const form = screen.getByRole("form", { name: "Add robot" });
    await user.type(within(form).getByLabelText("Operator host"), "x");
    await user.clear(within(form).getByLabelText("Port"));
    await user.type(within(form).getByLabelText("Port"), "abc");
    const camera = within(form).getByLabelText(/^camera$/i);
    await user.clear(camera);
    await user.type(camera, "rtsp://x");
    await user.click(within(form).getByRole("button", { name: /add robot/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid port; Bad camera");
    expect(callsTo("POST", "/robots")[0].body).toMatchObject({ socket_port: "abc" });
    expect(within(form).getByLabelText("Operator host")).toHaveValue("x");
  });

  it("edits a robot without changing its host", async () => {
    const { user, callsTo } = setup();
    await user.click(await screen.findByRole("button", { name: "Edit bluey.local" }));
    const form = screen.getByRole("form", { name: "Edit bluey.local" });
    expect(within(form).getByLabelText("Operator host")).toBeDisabled();
    expect(within(form).getByLabelText(/^camera$/i)).toHaveValue("rtsp://bluey.local:8554/camera");
    const port = within(form).getByLabelText("Port");
    await user.clear(port);
    await user.type(port, "5000");
    await user.click(within(form).getByRole("button", { name: /save robot/i }));
    await waitFor(() => expect(callsTo("PUT", "/robots/bluey.local")).toHaveLength(1));
    expect(callsTo("PUT", "/robots/bluey.local")[0].body).toMatchObject({ socket_port: 5000 });
    expect(callsTo("PUT", "/robots/bluey.local")[0].body).not.toHaveProperty("socket_host");
    expect(await screen.findByText(/:5000/)).toBeInTheDocument();
  });

  it("cancels editing", async () => {
    const { user } = setup();
    await user.click(await screen.findByRole("button", { name: "Edit bluey.local" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("form", { name: "Edit bluey.local" })).not.toBeInTheDocument();
  });

  it("deletes a robot after confirmation", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    const { user, callsTo } = setup();
    const remove = await screen.findByRole("button", { name: "Remove bluey.local" });
    await user.click(remove);
    expect(callsTo("DELETE", "/robots/bluey.local")).toHaveLength(0);
    await user.click(remove);
    await waitFor(() => expect(callsTo("DELETE", "/robots/bluey.local")).toHaveLength(1));
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(await screen.findByRole("form", { name: "Add robot" })).toBeInTheDocument();
  });

  it("saves only the changed defaults", async () => {
    const { user, callsTo, onChanged } = setup({
      robots: { "bluey.local": makeRobot("bluey.local"), "pi.local": makeRobot("pi.local") },
    });
    const save = await screen.findByRole("button", { name: /^save$/i });
    expect(save).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Camera 2 (optional)"), "pi.local");
    await user.click(screen.getByRole("radio", { name: "Debug" }));
    expect(screen.getByText(/Adds manual jog/)).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "Two screen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: "One-screen switching" })).not.toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: "Jog style" })).not.toBeInTheDocument();
    const slider = screen.getByRole("slider", { name: "Tracking model (local)" });
    expect(slider).toHaveAttribute("aria-valuetext", "Nano (yolo_nano)");
    fireEvent.change(slider, { target: { value: "1" } });
    fireEvent.keyUp(slider);
    await user.click(save);
    await waitFor(() => expect(callsTo("PUT", "/settings")).toHaveLength(1));
    expect(callsTo("PUT", "/settings")[0].body).toEqual({
      camera_2_host: "pi.local",
      ui_mode: "debug",
      default_model: "yolo_small",
    });
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalled();
  });

  it("does not offer Camera 1 as Camera 2", async () => {
    setup();
    const cam2 = await screen.findByLabelText("Camera 2 (optional)");
    expect(within(cam2).queryByRole("option", { name: "bluey.local" })).not.toBeInTheDocument();
  });

  it("warns that host and port changes need a restart", async () => {
    const { user } = setup();
    const port = await screen.findByLabelText("Web port");
    await user.clear(port);
    await user.type(port, "9000");
    expect(screen.getByText(/apply after restarting/)).toBeInTheDocument();
  });

  it("shows save errors", async () => {
    const { user } = setup({ routes: { "PUT /settings": () => errorResponse(422, "Invalid settings: nope") } });
    await user.click(await screen.findByRole("radio", { name: "Debug" }));
    await user.click(screen.getByRole("button", { name: /^save$/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid settings: nope");
  });

  it("shows load errors", async () => {
    setup({ routes: { "GET /settings": () => errorResponse(500, "boom") } });
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });

  it("closes with Escape, the close button and the backdrop", async () => {
    const { user, onClose } = setup();
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Close settings" }));
    await user.click(screen.getByRole("dialog"));
    expect(onClose).toHaveBeenCalledTimes(2);
    await user.click(screen.getByRole("dialog").parentElement!);
    expect(onClose).toHaveBeenCalledTimes(3);
  });
});
