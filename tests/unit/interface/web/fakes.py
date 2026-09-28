from types import SimpleNamespace

import numpy as np
import pytest

import src.config as config_module
from src.config.schema.app import AppSettingsFields
from src.config.schema.robot import ConnectionConfig
from src.connection.publisher import ERVTelemetrySnapshot
from src.observations.types import FramePacket
from src.talos_app import ControlMode


class FakePublisher:
    def __init__(self, connected=True, telemetry=None):
        self.connected = connected
        self.telemetry = telemetry or ERVTelemetrySnapshot(None, None, None, None)

    def is_connected(self):
        return self.connected

    def get_erv_telemetry_snapshot(self):
        return self.telemetry


class FakeVideo:
    def __init__(self, frame=None, sequence=0):
        self.frame = frame
        self.shape = frame.shape if frame is not None else None
        self.sequence = sequence

    def get_latest_packet(self):
        if self.frame is None:
            return None
        return FramePacket("cam", self.sequence, 0.0, self.frame)


class FakeConnection:
    def __init__(self, host, frame=None):
        self.host = host
        self.is_manual = True
        self.publisher = FakePublisher()
        self.video_connection = FakeVideo(frame)
        self.bboxes = []

    def get_bboxes(self):
        return self.bboxes


class FakeApp:
    """Records the Commander App calls the web backend makes."""

    def __init__(self, frame=None):
        self.connections: dict[str, FakeConnection] = {}
        self.active: str | None = None
        self.frame = frame if frame is not None else np.zeros((4, 6, 3), np.uint8)
        self.calls: list[tuple] = []
        self.model: str | None = None
        self.change_model_result = True
        self.control_mode = ControlMode.DISCRETE
        self.streamer = SimpleNamespace(get_frame=self._get_frame)
        self.streaming = False
        self.stream_error: Exception | None = None

    def _get_frame(self, host):
        conn = self.connections.get(host)
        return conn.video_connection.frame if conn else None

    def open_connection(self, host):
        self.calls.append(("open", host))
        self.connections[host] = FakeConnection(host, self.frame)
        self.active = host

    def disconnect_connection(self, host):
        self.calls.append(("disconnect", host))
        self.connections.pop(host, None)
        if self.active == host:
            self.active = next(iter(self.connections), None)

    def set_active_connection(self, host):
        self.active = host

    def get_active_connection(self):
        return self.connections.get(self.active) if self.active else None

    def move_home(self, hostname=None):
        self.calls.append(("home", hostname))

    def set_manual_control(self, manual, hostname=None):
        self.calls.append(("manual", manual, hostname))
        self.connections[hostname or self.active].is_manual = manual

    def get_manual_control(self, hostname=None):
        return self.connections[hostname or self.active].is_manual

    def change_model(self, option=None):
        self.calls.append(("model", option))
        if self.change_model_result:
            self.model = option
        return self.change_model_result

    def get_selected_model(self):
        return self.model

    def is_director_active(self):
        return bool(self.connections)

    def get_tracker_input_fps(self):
        return 12.345

    def get_tracker_output_fps(self):
        return 6.0

    def get_control_mode(self):
        return self.control_mode

    def set_control_mode(self, mode):
        self.calls.append(("jog_mode", str(mode)))
        self.control_mode = mode
        return mode

    def start_move(self, direction):
        self.calls.append(("start_move", direction.name, self.active))

    def stop_move(self, direction):
        self.calls.append(("stop_move", direction.name, self.active))

    def stop_all_movement(self):
        self.calls.append(("stop_all", self.active))

    def start_stream(self, streamer_type, hostname=None, fps=None, stream_config=None):
        self.calls.append(("start_stream", streamer_type, hostname))
        if self.stream_error is not None:
            raise self.stream_error
        self.streaming = True

    def stop_stream(self):
        self.calls.append(("stop_stream",))
        self.streaming = False

    def is_streaming(self):
        return self.streaming


def robot(host, **overrides):
    return ConnectionConfig(
        socket_host=host, socket_port=61616, camera_index=0, **overrides
    )


@pytest.fixture
def web_config(monkeypatch, tmp_path):
    """Isolated ROBOT_CONFIGS / APP_SETTINGS and YAML files for a test."""
    robots = {"a": robot("a"), "b": robot("b")}
    settings = AppSettingsFields()
    monkeypatch.setattr(config_module, "ROBOT_CONFIGS", robots, raising=False)
    monkeypatch.setattr(config_module, "APP_SETTINGS", settings, raising=False)
    import src.config.save as save_module

    app_settings_path = tmp_path / "app_settings.local.yaml"
    robot_configs_path = tmp_path / "robot_configs.local.yaml"
    monkeypatch.setattr(save_module, "APP_SETTINGS_PATH", str(app_settings_path))
    monkeypatch.setattr(save_module, "ROBOT_CONFIGS_PATH", str(robot_configs_path))
    import src.config.read as read_module

    monkeypatch.setattr(read_module, "ROBOT_CONFIGS_PATH", str(robot_configs_path))
    return SimpleNamespace(
        robots=robots,
        app_settings_path=app_settings_path,
        robot_configs_path=robot_configs_path,
    )
