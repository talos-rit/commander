import threading
import time
from typing import Any, Callable

import numpy as np
from loguru import logger

import src.config as config
from src.config.add import validate_connection_config
from src.config.save import remove_config, save_app_settings, update_config
from src.config.schema.app import AppSettingsFields
from src.config.schema.robot import ConnectionConfig
from src.connection.publisher import Direction
from src.talos_app import ControlMode
from src.tracking.pi_vision import PiVisionControl

from .state import ViewStateError, WebOperatorState

DEFAULT_TRACKING_MODEL = "yolo_nano"
JOG_MODES = ("discrete", "continuous")
JOINT_AXES = {"shoulder": 2, "elbow": 3}
# Direction.LEFT sends a negative azimuth, and that slews the camera to the
# operator's right. The jog pad, arrow keys, and gamepad all use these names,
# so swapping here keeps every control pointing the way the camera moves.
_OPERATOR_PAN = {Direction.LEFT: Direction.RIGHT, Direction.RIGHT: Direction.LEFT}


class BackendError(Exception):
    """A request that cannot be fulfilled; `status` maps to an HTTP code."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _seconds_since(monotonic_ts: float | None) -> float | None:
    if monotonic_ts is None:
        return None
    return round(time.monotonic() - monotonic_ts, 3)


class CommanderWebBackend:
    """
    Operator actions for the web UI, expressed against the shared Commander App.

    All mutating calls are serialized so HTTP handlers on different threads
    cannot interleave slot changes with connection open/close.
    """

    def __init__(
        self,
        app: Any,
        state: WebOperatorState,
        persist_settings: Callable[[dict[str, Any]], Any] = save_app_settings,
        model_options: Callable[[], list[str]] | None = None,
    ):
        self.app = app
        self.state = state
        self._persist_settings = persist_settings
        self._model_options = model_options or _default_model_options
        self._lock = threading.RLock()
        self._ready = threading.Event()
        self._cancel_startup = threading.Event()
        self._startup_thread: threading.Thread | None = None
        self._pi_vision: dict[str, PiVisionControl] = {}
        # Last Operator speed this UI sent. None until the operator sets it.
        # Home does not use this value.
        self._speed_percent: int | None = None

    # --- lifecycle -------------------------------------------------------

    @property
    def ready(self) -> bool:
        """False while startup() is still opening connections."""
        return self._ready.is_set()

    def start_in_background(self) -> threading.Thread:
        thread = threading.Thread(
            target=self._run_startup, name="commander-web-startup", daemon=True
        )
        self._startup_thread = thread
        thread.start()
        return thread

    def _run_startup(self) -> None:
        try:
            self.startup()
        except Exception:
            logger.exception("Commander web startup failed")

    def cancel_startup(self, timeout: float = 10.0) -> None:
        """Stop opening further connections and wait for the one in flight."""
        self._cancel_startup.set()
        thread = self._startup_thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            logger.info("Waiting for camera connections to settle before exiting...")
            thread.join(timeout)
            if thread.is_alive():
                logger.warning("Startup is still connecting; exiting anyway")
        for control in list(self._pi_vision.values()):
            control.close()
        self._pi_vision.clear()

    def startup(self) -> None:
        """Open the configured camera slots. One configured robot is enough."""
        try:
            self._startup()
        finally:
            self._ready.set()

    def _startup(self) -> None:
        with self._lock:
            for host in self.state.slots.values():
                if self._cancel_startup.is_set():
                    return
                self._ensure_connected(host)
            if self._cancel_startup.is_set():
                return
            self._apply_jog_mode(config.APP_SETTINGS.jog_mode)
            self._sync_active()
            # Load a saved model now. A saved Haar/MediaPipe name is replaced
            # with YOLO; with nothing saved, Auto-Track loads YOLO on demand.
            saved = config.APP_SETTINGS.default_model
            if saved and any(host not in self._pi_vision for host in self.app.connections):
                model = saved if saved in self._yolo_models() else self._preferred_model()
                if model:
                    self.app.change_model(model)

    def _ensure_connected(self, host: str) -> bool:
        if host in self.app.connections:
            self._ensure_pi_vision(host)
            return True
        if host not in config.ROBOT_CONFIGS:
            logger.warning(f"Camera slot host {host!r} has no robot config; skipping")
            return False
        self.app.open_connection(host)
        self._ensure_pi_vision(host)
        return host in self.app.connections

    def _ensure_pi_vision(self, host: str) -> None:
        robot = config.ROBOT_CONFIGS.get(host)
        if robot and robot.pi_vision_url and host in self.app.connections and host not in self._pi_vision:
            self.app.set_manual_control(True, hostname=host)
            control = PiVisionControl(self.app.connections[host].publisher, robot)
            self._pi_vision[host] = control
            control.start()

    def _stop_pi_vision(self, host: str | None, close: bool = False) -> None:
        control = self._pi_vision.get(host)
        if control:
            control.close() if close else control.set_enabled(False)
            if close:
                self._pi_vision.pop(host, None)

    def set_pi_vision_perception(self, enabled: bool, host: str | None = None) -> dict:
        with self._lock:
            target = self._target(host)
            control = self._pi_vision.get(target)
            if control is None:
                raise BackendError("Configure this robot's PiVision URL first", 409)
            try:
                return control.set_perception(enabled)
            except Exception as exc:
                raise BackendError(f"PiVision unavailable: {exc}", 502) from exc

    def set_pi_vision_tolerance(self, ratio: float, host: str | None = None) -> dict:
        with self._lock:
            target = self._target(host)
            control = self._pi_vision.get(target)
            if control is None:
                raise BackendError("Configure this robot's PiVision URL first", 409)
            try:
                return control.set_tolerance(ratio)
            except ValueError as exc:
                raise BackendError(str(exc), 422) from exc

    def _sync_active(self) -> None:
        """Keep App's active connection pointed at the operator's selected robot."""
        selected = self.state.selected_host
        if selected is not None and selected in self.app.connections:
            self.app.set_active_connection(selected)

    def _persist_view(self) -> None:
        try:
            self._persist_settings(self.state.persisted_settings())
        except Exception as exc:
            logger.warning(f"Could not persist web UI settings: {exc}")

    # --- status ----------------------------------------------------------

    def status(self) -> dict[str, Any]:
        with self._lock:
            hosts = list(dict.fromkeys([*self.state.slots.values(), *self.app.connections.keys()]))
            edge = self._pi_vision.get(self.state.selected_host)
            edge_status = edge.status() if edge else None
            return {
                "view": self.state.to_dict(),
                "connections": {host: self._host_status(host) for host in hosts},
                "tracking": {
                    "model": "pi_pose" if edge else self.app.get_selected_model(),
                    "model_options": self._yolo_models(),
                    "default_model": self._preferred_model(),
                    "director_active": edge_status["enabled"] if edge else self.app.is_director_active(),
                    "input_fps": round(edge_status.get("fps", 0), 1) if edge else round(self.app.get_tracker_input_fps(), 1),
                    "output_fps": round(edge_status.get("fps", 0), 1) if edge else round(self.app.get_tracker_output_fps(), 1),
                },
                "jog_mode": str(self.app.get_control_mode()),
                "speed_percent": self._speed_percent,
                "virtual_camera": self.app.is_streaming(),
                "robots": sorted(config.ROBOT_CONFIGS.keys()),
            }

    def _host_status(self, host: str) -> dict[str, Any]:
        conn = self.app.connections.get(host)
        robot_config = config.ROBOT_CONFIGS.get(host)
        base = {
            "host": host,
            "slot": self.state.slot_of(host),
            "configured": robot_config is not None,
            "open": conn is not None,
            "manual_only": bool(robot_config.manual_only) if robot_config else False,
        }
        if conn is None:
            return {
                **base,
                "operator_connected": False,
                "has_video": False,
                "auto_tracking": False,
                "telemetry": None,
            }
        video = conn.video_connection
        publisher = conn.publisher
        is_connected = getattr(publisher, "is_connected", None)
        return {
            **base,
            "operator_connected": bool(is_connected()) if callable(is_connected) else False,
            "has_video": video is not None and video.shape is not None,
            "auto_tracking": self._pi_vision[host].status()["enabled"] if host in self._pi_vision else not conn.is_manual,
            "subjects": self._pi_vision[host].status()["subjects"] if host in self._pi_vision else len(conn.get_bboxes() or []),
            "pi_vision": self._pi_vision[host].status() if host in self._pi_vision else None,
            "telemetry": self._telemetry(publisher),
        }

    @staticmethod
    def _telemetry(publisher: Any) -> dict[str, Any] | None:
        getter = getattr(publisher, "get_erv_telemetry_snapshot", None)
        if not callable(getter):
            return None
        snapshot = getter()
        return {
            "encoder_counts": list(snapshot.encoder_counts)
            if snapshot.encoder_counts is not None
            else None,
            "encoder_age_s": _seconds_since(snapshot.encoder_received_monotonic),
            "joint_counts": list(snapshot.joint_counts)
            if snapshot.joint_counts is not None
            else None,
            "joint_age_s": _seconds_since(snapshot.joint_received_monotonic),
        }

    # --- view ------------------------------------------------------------

    def set_view(
        self,
        display_mode: str | None = None,
        one_screen_mode: str | None = None,
        ui_mode: str | None = None,
    ) -> None:
        with self._lock:
            try:
                if display_mode is not None:
                    self.state.set_display_mode(display_mode)
                if one_screen_mode is not None:
                    self.state.set_one_screen_mode(one_screen_mode)
                if ui_mode is not None:
                    self.state.set_ui_mode(ui_mode)
            except ViewStateError as exc:
                raise BackendError(str(exc), 409) from exc
            if self.state.ui_mode != "debug":
                self._stop_jog()
            self._sync_active()
            self._persist_view()

    def assign_slots(self, camera_1: str | None, camera_2: str | None) -> None:
        with self._lock:
            for host in (camera_1, camera_2):
                if host and host not in config.ROBOT_CONFIGS:
                    raise BackendError(f"No robot config named {host!r}", 404)
            previous = set(self.state.slots.values())
            self.state.assign_slots(camera_1, camera_2)
            current = set(self.state.slots.values())
            for host in previous - current:
                self._stop_pi_vision(host, close=True)
                if host in self.app.connections:
                    self.app.disconnect_connection(host)
            for host in current:
                self._ensure_connected(host)
            self._sync_active()
            self._persist_view()

    def select(self, host: str | None = None, slot: int | None = None) -> None:
        with self._lock:
            previous = self.state.selected_host
            try:
                if slot is not None:
                    self.state.select_slot(slot)
                elif host is not None:
                    self.state.select_host(host)
                else:
                    raise BackendError("Provide a host or slot to select")
            except ViewStateError as exc:
                raise BackendError(str(exc), 409) from exc
            if previous != self.state.selected_host:
                self._stop_pi_vision(previous)
            self._stop_jog()
            self._sync_active()

    # --- control ---------------------------------------------------------

    def _target(self, host: str | None) -> str:
        target = host or self.state.selected_host
        if target is None:
            raise BackendError("No camera is assigned; open Settings to add one", 409)
        if target not in self.app.connections:
            raise BackendError(f"{target!r} is not connected", 409)
        return target

    def clear_robot_error(self, host: str | None = None) -> str:
        with self._lock:
            target = self._target(host)
            self._stop_pi_vision(target)
            self.app.connections[target].publisher.erv_enable_control()
            return target

    def home(self, host: str | None = None) -> str:
        with self._lock:
            target = self._target(host)
            self._stop_pi_vision(target)
            # A tracking director would immediately steer away from home.
            self.app.set_manual_control(True, hostname=target)
            self.app.move_home(hostname=target)
            return target

    def set_auto_track(self, enabled: bool, host: str | None = None) -> bool:
        with self._lock:
            target = self._target(host)
            robot_config = config.ROBOT_CONFIGS.get(target)
            if enabled and robot_config is not None and robot_config.manual_only:
                raise BackendError(f"{target!r} is configured as manual only", 409)
            if target in self._pi_vision:
                if enabled:
                    if target != self.state.selected_host:
                        raise BackendError("Select this robot before enabling PiVision tracking", 409)
                    self._stop_jog()
                    self._pi_vision[target].manual_handoff()
                self.app.set_manual_control(True, hostname=target)
                try:
                    return self._pi_vision[target].set_enabled(enabled)
                except ValueError as exc:
                    raise BackendError(str(exc), getattr(exc, "status", 409)) from exc
            if enabled and self.app.get_selected_model() is None:
                model = self._preferred_model()
                if model is None:
                    raise BackendError(
                        "YOLO is not installed, so there is no tracking model. "
                        "Install it with `uv sync --extra yolo` and restart commander-web.",
                        500,
                    )
                if not self.app.change_model(model):
                    raise BackendError(f"Could not load tracking model {model!r}", 500)
            self.app.set_manual_control(not enabled, hostname=target)
            return not bool(self.app.get_manual_control(hostname=target))

    def set_virtual_camera(self, enabled: bool) -> bool:
        """Stream the selected camera out as a virtual webcam, or stop doing so.

        The stream follows whichever robot is selected, so changing the
        controlled camera switches the virtual camera too. Both cameras are
        assumed to share a resolution; the device is sized from the first frame.
        """
        with self._lock:
            if not enabled:
                self.app.stop_stream()
                return False
            target = self._target(None)
            video = self.app.connections[target].video_connection
            if video is None or getattr(video, "shape", None) is None:
                raise BackendError(f"{target} has no video to stream yet", 409)
            self._sync_active()
            try:
                self.app.start_stream(streamer_type="pyvcam")
            except RuntimeError as exc:
                detail = str(exc).strip().splitlines()[0] or "unknown error"
                raise BackendError(
                    "Could not start the virtual camera. Install OBS and start its "
                    f"Virtual Camera, then try again. ({detail})",
                    500,
                ) from exc
            if not self.app.is_streaming():
                raise BackendError("Could not start the virtual camera", 500)
            return True

    def _require_debug(self) -> None:
        if self.state.ui_mode != "debug":
            raise BackendError("Manual controls are only available in debug mode", 403)

    def move(self, direction: str, active: bool) -> None:
        with self._lock:
            self._require_debug()
            try:
                parsed = Direction[direction.upper()]
            except KeyError as exc:
                raise BackendError(f"Unknown direction {direction!r}") from exc
            parsed = _OPERATOR_PAN.get(parsed, parsed)
            self._target(None)
            self._stop_pi_vision(self.state.selected_host)
            self._sync_active()
            if active:
                self.app.start_move(parsed)
            else:
                self.app.stop_move(parsed)

    def joint_jog(self, axis: str, direction: int, active: bool) -> None:
        """Hold or release an ER-V shoulder or elbow jog. Wrist roll is not exposed."""
        joint = JOINT_AXES.get(axis)
        if joint is None:
            raise BackendError(f"Unknown joint {axis!r}")
        if direction not in (-1, 1):
            raise BackendError(f"Joint direction must be -1 or 1, got {direction!r}")
        with self._lock:
            self._require_debug()
            self._target(None)
            self._stop_pi_vision(self.state.selected_host)
            self._sync_active()
            if active:
                self.app.start_joint_jog(joint, direction)
            else:
                self.app.stop_joint_jog()

    def cartesian(self, x: int, y: int, z: int, active: bool) -> None:
        """Hold or release a Cartesian move. Each axis is -1, 0, or 1."""
        vector = (x, y, z)
        if any(component not in (-1, 0, 1) for component in vector):
            raise BackendError(f"Cartesian components must be -1, 0, or 1, got {vector!r}")
        with self._lock:
            self._require_debug()
            self._target(None)
            self._stop_pi_vision(self.state.selected_host)
            self._sync_active()
            if active and vector != (0, 0, 0):
                self.app.start_cartesian(*vector)
            else:
                self.app.stop_cartesian()

    def stop_motion(self) -> None:
        """Stop polar, Cartesian, and joint jogs. Home is left alone."""
        with self._lock:
            self._require_debug()
            self._target(None)
            self._sync_active()
            self.app.stop_all_movement()

    def enable_control(self) -> None:
        """Ask the Operator to re-enable ER-V servo control (ACL CON)."""
        with self._lock:
            self._require_debug()
            publisher = self._operator_publisher()
            publisher.erv_enable_control()

    def set_speed_percent(self, percent: int) -> int:
        """Set the Operator speed used by manual moves. Home is unaffected."""
        if not isinstance(percent, int) or not 1 <= percent <= 100:
            raise BackendError("Speed must be from 1 to 100", 422)
        with self._lock:
            self._require_debug()
            publisher = self._operator_publisher()
            try:
                publisher.erv_set_speed_percent(percent)
            except ValueError as exc:
                raise BackendError(str(exc), 422) from exc
            self._speed_percent = percent
            return percent

    def _operator_publisher(self):
        self._target(None)
        self._sync_active()
        connection = self.app.get_active_connection()
        if connection is None or getattr(connection, "publisher", None) is None:
            raise BackendError("The selected robot is not connected", 409)
        return connection.publisher

    def _apply_jog_mode(self, mode: str) -> None:
        if self.app.get_active_connection() is not None:
            self.app.set_control_mode(ControlMode(mode))
        else:
            self.app.control_mode = ControlMode(mode)

    def _stop_jog(self) -> None:
        if self.app.get_active_connection() is not None:
            self.app.stop_all_movement()

    def set_jog_mode(self, mode: str) -> str:
        with self._lock:
            if mode not in JOG_MODES:
                raise BackendError(f"Unknown jog mode {mode!r}")
            self._apply_jog_mode(mode)
            try:
                self._persist_settings({"jog_mode": mode})
            except Exception as exc:
                logger.warning(f"Could not persist jog mode: {exc}")
            return mode

    def _yolo_models(self) -> list[str]:
        """Models the web UI will load. Haar and MediaPipe are not offered."""
        return [name for name in self._model_options() if str(name).startswith("yolo")]

    def _preferred_model(self) -> str | None:
        options = self._yolo_models()
        saved = config.APP_SETTINGS.default_model
        if saved in options:
            return saved
        if DEFAULT_TRACKING_MODEL in options:
            return DEFAULT_TRACKING_MODEL
        return options[0] if options else None

    def set_model(self, model: str | None) -> str | None:
        with self._lock:
            if model is not None and model not in self._yolo_models():
                raise BackendError(f"Unknown model {model!r}", 404)
            if not self.app.change_model(model):
                raise BackendError("Model change failed; is a camera connected?", 409)
            return self.app.get_selected_model()

    # --- video -----------------------------------------------------------

    def get_frame(self, host: str) -> np.ndarray | None:
        if host not in self.app.connections:
            return None
        frame = self.app.streamer.get_frame(host)
        control = self._pi_vision.get(host)
        return control.annotate_frame(frame) if control is not None and frame is not None else frame

    def frame_sequence(self, host: str) -> int | None:
        conn = self.app.connections.get(host)
        video = conn.video_connection if conn is not None else None
        packet = video.get_latest_packet() if video is not None else None
        return packet.frame_sequence if packet is not None else None

    def frame_fps(self, host: str) -> int:
        robot_config = config.ROBOT_CONFIGS.get(host)
        return robot_config.fps if robot_config is not None else 30

    # --- settings --------------------------------------------------------

    def get_settings(self) -> dict[str, Any]:
        return config.APP_SETTINGS.model_dump()

    def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            try:
                AppSettingsFields.model_validate(
                    {**config.APP_SETTINGS.model_dump(), **updates}
                )
            except Exception as exc:
                raise BackendError(f"Invalid settings: {exc}", 422) from exc
            slot_keys = {"camera_1_host", "camera_2_host"}
            view_keys = {"display_mode", "one_screen_mode", "ui_mode"}
            if slot_keys & updates.keys():
                self.assign_slots(
                    updates.get("camera_1_host", self.state.camera_1),
                    updates.get("camera_2_host", self.state.camera_2),
                )
            view_updates = {k: updates[k] for k in view_keys & updates.keys()}
            if view_updates:
                # A saved two-screen default is allowed without a second camera;
                # it applies once Camera 2 is assigned.
                if view_updates.get("display_mode") == "two_screen" and not self.state.has_two_cameras:
                    self.state.display_mode = "two_screen"
                    view_updates.pop("display_mode")
                self.set_view(**view_updates)
            if "jog_mode" in updates:
                self.set_jog_mode(updates["jog_mode"])
            rest = {
                k: v
                for k, v in updates.items()
                if k not in slot_keys | view_keys | {"jog_mode"}
            }
            try:
                self._persist_settings({**rest, **self.state.persisted_settings()})
            except Exception as exc:
                raise BackendError(f"Invalid settings: {exc}", 422) from exc
            return self.get_settings()

    def list_robots(self) -> dict[str, dict[str, Any]]:
        return {
            host: robot_config.model_dump()
            for host, robot_config in sorted(config.ROBOT_CONFIGS.items())
        }

    def add_robot(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            data = dict(data)
            valid, robot_config, errors = validate_connection_config(
                data.pop("socket_host", ""),
                data.pop("socket_port", ""),
                data.pop("camera_index", ""),
                **data,
            )
            if not valid or robot_config is None:
                raise BackendError("; ".join(errors), 422)
            update_config(robot_config.socket_host, robot_config)
            if self.state.camera_1 is None:
                self.assign_slots(robot_config.socket_host, None)
            return robot_config.model_dump()

    def update_robot(self, host: str, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            existing = config.ROBOT_CONFIGS.get(host)
            if existing is None:
                raise BackendError(f"No robot config named {host!r}", 404)
            merged = {**existing.model_dump(), **data, "socket_host": host}
            try:
                robot_config = ConnectionConfig(**merged)
            except Exception as exc:
                raise BackendError(str(exc), 422) from exc
            update_config(host, robot_config)
            if host in self.app.connections:
                # Reopen so camera/port changes take effect.
                self._stop_pi_vision(host, close=True)
                self.app.disconnect_connection(host)
                self._ensure_connected(host)
                self._sync_active()
            return robot_config.model_dump()

    def delete_robot(self, host: str) -> None:
        with self._lock:
            if host not in config.ROBOT_CONFIGS:
                raise BackendError(f"No robot config named {host!r}", 404)
            if host in self.state.slots.values():
                remaining = [h for h in self.state.slots.values() if h != host]
                self.assign_slots(remaining[0] if remaining else None, None)
            elif host in self.app.connections:
                self._stop_pi_vision(host, close=True)
                self.app.disconnect_connection(host)
            remove_config(host)


def _default_model_options() -> list[str]:
    from src.tracking.options import MODEL_OPTIONS

    return list(MODEL_OPTIONS)
