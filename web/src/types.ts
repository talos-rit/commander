export type DisplayMode = "one_screen" | "two_screen";
export type OneScreenMode = "dynamic" | "manual";
export type UIMode = "simple" | "debug";
export type JogMode = "discrete" | "continuous";
export type Direction = "up" | "down" | "left" | "right";
export type Slot = 1 | 2;

export interface ViewState {
  camera_1: string | null;
  camera_2: string | null;
  available_slots: 0 | 1 | 2;
  display_mode: DisplayMode;
  preferred_display_mode: DisplayMode;
  one_screen_mode: OneScreenMode;
  ui_mode: UIMode;
  displayed_slot: Slot | null;
  displayed_hosts: string[];
  selected_host: string | null;
}

export interface Telemetry {
  encoder_counts: number[] | null;
  encoder_age_s: number | null;
  joint_counts: number[] | null;
  joint_age_s: number | null;
}

export interface HostStatus {
  host: string;
  slot: Slot | null;
  configured: boolean;
  open: boolean;
  manual_only: boolean;
  operator_connected: boolean;
  has_video: boolean;
  auto_tracking: boolean;
  subjects?: number;
  telemetry: Telemetry | null;
}

export interface TrackingStatus {
  model: string | null;
  model_options: string[];
  /** Model Auto-Track loads when none is loaded; null when YOLO is not installed. */
  default_model: string | null;
  director_active: boolean;
  input_fps: number;
  output_fps: number;
}

export interface Status {
  view: ViewState;
  connections: Record<string, HostStatus>;
  tracking: TrackingStatus;
  jog_mode: JogMode;
  /** True while the selected camera is being sent to a virtual webcam. */
  virtual_camera: boolean;
  robots: string[];
}

export interface AppSettings {
  log_level: string;
  bbox_max_fps: number;
  frame_process_fps: number;
  disable_performance_warnings: boolean;
  web_host: string;
  web_port: number;
  ui_mode: UIMode;
  display_mode: DisplayMode;
  one_screen_mode: OneScreenMode;
  camera_1_host: string | null;
  camera_2_host: string | null;
  default_model: string | null;
  jog_mode: JogMode;
}

export interface RobotConfig {
  socket_host: string;
  socket_port: number;
  camera_index: number | string;
  acceptable_box_percent: number;
  vertical_field_of_view: number;
  horizontal_field_of_view: number;
  confirmation_delay: number;
  command_delay: number;
  fps: number;
  frame_width: number;
  frame_height: number | null;
  max_fps: number;
  manual_only: boolean;
}

/** Form input; a non-numeric port is sent as-is so the backend can report it. */
export type RobotInput = Pick<RobotConfig, "socket_host" | "camera_index"> & { socket_port: number | string } & Partial<
    Omit<RobotConfig, "socket_host" | "socket_port" | "camera_index">
  >;
