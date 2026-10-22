import type {
  AppSettings,
  Direction,
  DisplayMode,
  JogMode,
  OneScreenMode,
  RobotConfig,
  RobotInput,
  Slot,
  Status,
  UIMode,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    /** The backend is up but still opening camera connections. */
    readonly starting = false,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function describeDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === "object" && item && "msg" in item ? String(item.msg) : String(item)))
      .join("; ");
  }
  return "Request failed";
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Commander backend is unreachable", 0);
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(describeDetail(data?.detail), response.status, data?.starting === true);
  }
  return data as T;
}

export const api = {
  status: () => request<Status>("GET", "/status"),

  setView: (view: { display_mode?: DisplayMode; one_screen_mode?: OneScreenMode; ui_mode?: UIMode }) =>
    request<Status>("POST", "/view", view),
  assignSlots: (camera_1: string | null, camera_2: string | null) =>
    request<Status>("POST", "/cameras/slots", { camera_1, camera_2 }),
  select: (target: { host?: string; slot?: Slot }) => request<Status>("POST", "/cameras/select", target),

  clearRobotError: (host?: string) => request<{ host: string }>("POST", "/control/clear-error", host ? { host } : {}),
  home: (host?: string) => request<{ host: string }>("POST", "/control/home", host ? { host } : {}),
  setAutoTrack: (enabled: boolean, host?: string) =>
    request<{ enabled: boolean }>("POST", "/control/auto-track", { enabled, host }),
  setPiVisionPerception: (enabled: boolean, host?: string) =>
    request<{ enabled: boolean }>("PUT", "/control/pi-vision/perception", { enabled, host }),
  setPiVisionTolerance: (acceptable_ratio: number, host?: string) =>
    request<{ acceptable_ratio: number }>("PUT", "/control/pi-vision/tuning", { acceptable_ratio, host }),
  moveStart: (direction: Direction) => request<{ ok: boolean }>("POST", "/control/move/start", { direction }),
  moveStop: (direction: Direction) => request<{ ok: boolean }>("POST", "/control/move/stop", { direction }),
  jointStart: (axis: "shoulder" | "elbow", direction: -1 | 1) =>
    request<{ ok: boolean }>("POST", "/control/joint/start", { axis, direction }),
  jointStop: () => request<{ ok: boolean }>("POST", "/control/joint/stop"),
  cartesianStart: (x: -1 | 0 | 1, y: -1 | 0 | 1, z: -1 | 0 | 1) =>
    request<{ ok: boolean }>("POST", "/control/cartesian/start", { x, y, z }),
  cartesianStop: () => request<{ ok: boolean }>("POST", "/control/cartesian/stop"),
  stopMotion: () => request<{ ok: boolean }>("POST", "/control/stop"),
  enableControl: () => request<{ ok: boolean }>("POST", "/control/enable"),
  setSpeed: (percent: number) => request<{ percent: number }>("POST", "/control/speed", { percent }),
  setJogMode: (mode: JogMode) => request<{ mode: JogMode }>("POST", "/control/jog-mode", { mode }),
  setModel: (model: string | null) => request<{ model: string | null }>("POST", "/control/model", { model }),
  setVirtualCamera: (enabled: boolean) =>
    request<{ enabled: boolean }>("POST", "/control/virtual-camera", { enabled }),

  settings: () => request<AppSettings>("GET", "/settings"),
  updateSettings: (updates: Partial<AppSettings>) => request<AppSettings>("PUT", "/settings", updates),

  robots: () => request<Record<string, RobotConfig>>("GET", "/robots"),
  addRobot: (robot: RobotInput) => request<RobotConfig>("POST", "/robots", robot),
  updateRobot: (host: string, robot: Partial<Omit<RobotInput, "socket_host">>) =>
    request<RobotConfig>("PUT", `/robots/${encodeURIComponent(host)}`, robot),
  deleteRobot: (host: string) => request<void>("DELETE", `/robots/${encodeURIComponent(host)}`),
};

export const mjpegUrl = (host: string) => `/api/cameras/${encodeURIComponent(host)}/mjpeg`;
