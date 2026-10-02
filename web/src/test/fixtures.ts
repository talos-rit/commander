import { vi } from "vitest";
import type { AppSettings, HostStatus, RobotConfig, Status, ViewState } from "../types";

export function hostStatus(host: string, overrides: Partial<HostStatus> = {}): HostStatus {
  return {
    host,
    slot: 1,
    configured: true,
    open: true,
    manual_only: false,
    operator_connected: true,
    has_video: false,
    auto_tracking: false,
    subjects: 0,
    telemetry: null,
    ...overrides,
  };
}

export function makeStatus({
  hosts = ["bluey.local"],
  view = {},
  connections = {},
  ...rest
}: {
  hosts?: string[];
  view?: Partial<ViewState>;
  connections?: Record<string, Partial<HostStatus>>;
} & Partial<Omit<Status, "view" | "connections">> = {}): Status {
  const [camera_1 = null, camera_2 = null] = hosts;
  const available = hosts.length as 0 | 1 | 2;
  const display_mode = view.display_mode ?? "one_screen";
  const displayed_slot = available ? (view.displayed_slot ?? 1) : null;
  const displayed_hosts =
    view.displayed_hosts ??
    (available === 0 ? [] : display_mode === "two_screen" ? hosts : [hosts[(displayed_slot ?? 1) - 1]]);
  return {
    view: {
      camera_1,
      camera_2,
      available_slots: available,
      display_mode,
      preferred_display_mode: display_mode,
      one_screen_mode: "manual",
      ui_mode: "simple",
      displayed_slot,
      displayed_hosts,
      selected_host: displayed_hosts[0] ?? null,
      ...view,
    },
    connections: Object.fromEntries(
      hosts.map((host, i) => [host, hostStatus(host, { slot: (i + 1) as 1 | 2, ...connections[host] })]),
    ),
    tracking: {
      model: null,
      model_options: ["basic", "yolo_nano", "yolo_small", "yolo_medium", "yolo_large", "yolo_xlarge"],
      default_model: "yolo_nano",
      director_active: false,
      input_fps: 0,
      output_fps: 0,
    },
    jog_mode: "discrete",
    virtual_camera: false,
    robots: hosts,
    ...rest,
  };
}

export function makeSettings(overrides: Partial<AppSettings> = {}): AppSettings {
  return {
    log_level: "INFO",
    bbox_max_fps: 30,
    frame_process_fps: 15,
    disable_performance_warnings: false,
    web_host: "127.0.0.1",
    web_port: 8000,
    ui_mode: "simple",
    display_mode: "one_screen",
    one_screen_mode: "manual",
    camera_1_host: null,
    camera_2_host: null,
    default_model: null,
    jog_mode: "discrete",
    ...overrides,
  };
}

export function makeRobot(host: string, overrides: Partial<RobotConfig> = {}): RobotConfig {
  return {
    socket_host: host,
    socket_port: 61616,
    camera_index: `rtsp://${host}:8554/camera`,
    acceptable_box_percent: 0.3,
    vertical_field_of_view: 48,
    horizontal_field_of_view: 64,
    confirmation_delay: 0,
    command_delay: 0,
    fps: 30,
    frame_width: 1280,
    frame_height: null,
    max_fps: 30,
    manual_only: false,
    ...overrides,
  };
}

export interface Call {
  method: string;
  path: string;
  body: unknown;
}

type Handler = (call: Call) => unknown | Response;

/** Replaces fetch with a router keyed by "METHOD /path" (path without /api). */
export function mockApi(routes: Record<string, Handler | unknown>) {
  const calls: Call[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const path = url.pathname.replace(/^\/api/, "");
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    const call = { method, path, body };
    calls.push(call);
    const key = `${method} ${path}`;
    const route = routes[key];
    if (!(key in routes)) {
      return new Response(JSON.stringify({ detail: `No mock for ${method} ${path}` }), { status: 404 });
    }
    const result = typeof route === "function" ? await (route as Handler)(call) : route;
    if (result instanceof Response) return result;
    if (result === undefined) return new Response(null, { status: 204 });
    return new Response(JSON.stringify(result), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return {
    calls,
    fetchMock,
    callsTo: (method: string, path: string) => calls.filter((c) => c.method === method && c.path === path),
  };
}

export function errorResponse(status: number, detail: unknown) {
  return new Response(JSON.stringify({ detail }), { status, headers: { "Content-Type": "application/json" } });
}
