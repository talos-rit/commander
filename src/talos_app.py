from enum import StrEnum
from multiprocessing.managers import SharedMemoryManager

from loguru import logger

from src.streaming import StreamController, StreamControllerFactory

from . import config
from .config.schema.robot import ConnectionConfig
from .connection.connection import (
    Connection,
    ConnectionCollection,
    VideoConnection,
    is_live_source,
)
from .connection.publisher import Direction
from .directors import BaseDirector, ContinuousDirector
from .observations.replay import ObservationRecorder
from .scheduler import IterativeTask, Scheduler
from .streaming.streamer import Streamer
from .thread_scheduler import ThreadScheduler
from .tracking import USABLE_MODELS
from .tracking.tracker import Tracker


class ControlMode(StrEnum):
    CONTINUOUS = "continuous"
    DISCRETE = "discrete"


DIRECTION_MAP = {
    Direction.UP: (0, 10),
    Direction.DOWN: (0, -10),
    Direction.LEFT: (-10, 0),
    Direction.RIGHT: (10, 0),
}

# Operator drops a held joint jog after about 500 ms unless the start is repeated.
JOINT_JOG_REFRESH_MS = 200
# Discrete Cartesian steps, in the same units polar discrete uses for tenths of a degree.
CARTESIAN_STEP = 10


class App:
    scheduler: Scheduler
    connections: ConnectionCollection
    tracker: Tracker
    streamer: Streamer
    director: BaseDirector | None = None
    control_mode: ControlMode = ControlMode.CONTINUOUS
    model_selection: str | None = None
    move_delay_ms: int = 300  # time inbetween each directional command being sent while directional button is depressed

    # State for continuous and discrete movements
    current_continuous_directions: set[Direction] = set()
    discrete_move_task: dict[Direction, IterativeTask] = {}
    _streamer: StreamController | None = None

    def __init__(
        self,
        scheduler: Scheduler = ThreadScheduler(),
        smm: SharedMemoryManager = SharedMemoryManager(),
        args=None,
        observation_recorder: ObservationRecorder | None = None,
    ) -> None:
        self.scheduler = scheduler
        self.connections = ConnectionCollection()
        tracker_options = (
            {"observation_recorder": observation_recorder}
            if observation_recorder is not None
            else {}
        )
        self.tracker = Tracker(
            self.connections, scheduler=scheduler, smm=smm, **tracker_options
        )
        self._cli_draw_bboxes = bool(args.draw_bboxes) if args else False
        self._joint_jog: tuple[int, int] | None = None
        self._joint_jog_task: IterativeTask | None = None
        self._cartesian: tuple[int, int, int] | None = None
        self._cartesian_task: IterativeTask | None = None
        self.streamer = Streamer(self.connections, draw_bboxes=self._cli_draw_bboxes)
        self.director = ContinuousDirector(
            self.tracker, self.connections, self.scheduler
        )
        if args:
            if args.connection is not None:
                self.open_connection(args.connection)
            if len(self.connections) > 0:
                if args.model is not None:
                    self.change_model(args.model)
                if args.control_mode is not None:
                    self.set_manual_control(args.control_mode == "manual")
                if args.director is not None:
                    self.set_control_mode(ControlMode(args.director))

    def open_connection(
        self,
        hostname: str,
    ) -> None:
        """
        Opens a connection to the given hostname.
        If port or camera is not provided, uses the values from the config.
        """
        logger.info(f"Opening connection to {hostname}")
        if hostname in self.connections:
            return logger.warning(f"Connection to {hostname} already exists")
        if (conf := config.ROBOT_CONFIGS.get(hostname)) is None:
            return logger.error(
                f"Connection hostname {hostname} not found in config, not opening connection"
            )
        try:
            video_connection = VideoConnection(
                src=conf.camera_index,
                background_capture=is_live_source(conf.camera_index),
            )
        except Exception as exc:
            logger.warning(f"Failed to open video connection for {hostname}: {exc}")
            video_connection = None
        if isinstance(conf.pi_vision_url, str) and conf.pi_vision_url:
            from .connection.edge_publisher import EdgePublisher
            conn = Connection(hostname, conf.socket_port, video_connection,
                              publisher_factory=lambda _host, _port: EdgePublisher(conf.pi_vision_url))
        else:
            conn = Connection(hostname, conf.socket_port, video_connection)
        self.connections[hostname] = conn

    def start_move(self, direction: Direction) -> None:
        """
        Starts movement in the given direction.
        In continuous mode, starts continuous movement.
        In discrete mode, starts sending discrete movement commands at intervals.
        """
        if (connection := self.get_active_connection()) is None:
            return logger.error("No connection found")
        if not connection.is_manual:
            return logger.error(
                f"Active connection {connection.host} is not in manual mode"
            )
        if self.control_mode == ControlMode.CONTINUOUS:
            return self.continuous_move(direction)
        if self.discrete_move_task.get(direction) is not None:
            return
        self.discrete_move_task[direction] = self.scheduler.set_interval(
            self.move_delay_ms, self.discrete_move, direction
        )

    def discrete_move(self, direction: Direction) -> None:
        """Sends a single discrete movement command in the given direction."""
        if (connection := self.get_active_connection()) is None:
            return logger.error(f"No connection found for {connection=}")
        logger.info(f"Polar pan discrete {direction.name.lower()}")
        connection.publisher.polar_pan_discrete(*DIRECTION_MAP[direction], 1000, 3000)

    def continuous_move(self, direction: Direction) -> None:
        """
        Starts continuous movement in the given direction.
        This will merge with any existing continuous movements.
        """
        if direction in self.current_continuous_directions:
            return
        if (connection := self.get_active_connection()) is None:
            return logger.error("No connection found")
        self.current_continuous_directions.add(direction)
        publisher = connection.publisher
        publisher.polar_pan_continuous_direction_start(
            sum(self.current_continuous_directions)
        )

    def stop_move(self, direction: Direction) -> None:
        """Stops continuous movement if in continuous mode and no keys are pressed."""
        if self.control_mode == ControlMode.CONTINUOUS:
            return self.stop_continuous_move(direction)
        if self.discrete_move_task.get(direction) is not None:
            return self.discrete_move_task.pop(direction).cancel()

    def stop_continuous_move(self, direction: Direction) -> None:
        """Release one held polar direction and update the remaining vector."""
        logger.debug(f"continuous {self.current_continuous_directions}")
        self.current_continuous_directions.discard(direction)
        if (connection := self.get_active_connection()) is None:
            return logger.error("No connection found")
        if self.current_continuous_directions:
            return connection.publisher.polar_pan_continuous_direction_start(
                sum(self.current_continuous_directions)
            )
        return connection.publisher.polar_pan_continuous_stop()

    def start_joint_jog(self, axis: int, direction: int) -> None:
        """Hold an ER-V shoulder (axis 2) or elbow (axis 3) jog. One joint at a time."""
        if axis not in (2, 3) or direction not in (-1, 1):
            return logger.error(f"Invalid joint jog {axis=} {direction=}")
        if (publisher := self._manual_publisher()) is None:
            return
        if self._joint_jog == (axis, direction):
            return
        self._cancel_joint_jog_task()
        if self._joint_jog is not None:
            publisher.erv_joint_jog_stop()
        logger.info(f"Joint jog axis {axis} direction {direction}")
        publisher.erv_joint_jog_start(axis, direction)
        self._joint_jog = (axis, direction)
        self._joint_jog_task = self.scheduler.set_interval(
            JOINT_JOG_REFRESH_MS, self._refresh_joint_jog
        )

    def stop_joint_jog(self) -> None:
        """Stop a held shoulder or elbow jog."""
        if self._joint_jog is None and self._joint_jog_task is None:
            return
        self._cancel_joint_jog_task()
        self._joint_jog = None
        if (connection := self.get_active_connection()) is None:
            return logger.error("No connection found")
        connection.publisher.erv_joint_jog_stop()

    def _refresh_joint_jog(self) -> None:
        if self._joint_jog is None:
            return
        if (connection := self.get_active_connection()) is None:
            return
        axis, direction = self._joint_jog
        connection.publisher.erv_joint_jog_start(axis, direction)

    def _cancel_joint_jog_task(self) -> None:
        if self._joint_jog_task is not None:
            self._joint_jog_task.cancel()
            self._joint_jog_task = None

    def start_cartesian(self, x: int, y: int, z: int) -> None:
        """
        Hold a Cartesian move. Each component is -1, 0, or 1.
        Y- extends the arm (away from the base) and Y+ retracts it.
        """
        vector = (x, y, z)
        if any(component not in (-1, 0, 1) for component in vector) or vector == (0, 0, 0):
            return logger.error(f"Invalid cartesian jog {vector}")
        if self._manual_publisher() is None:
            return
        if self._cartesian == vector:
            return
        self._cancel_cartesian_task()
        self._cartesian = vector
        logger.info(f"Cartesian jog x={x} y={y} z={z}")
        if self.control_mode == ControlMode.CONTINUOUS:
            return self._publish_cartesian_continuous()
        self._cartesian_task = self.scheduler.set_interval(
            self.move_delay_ms, self._publish_cartesian_discrete
        )

    def stop_cartesian(self) -> None:
        """Stop a held Cartesian move."""
        if self._cartesian is None and self._cartesian_task is None:
            return
        was_continuous = self.control_mode == ControlMode.CONTINUOUS
        self._cancel_cartesian_task()
        self._cartesian = None
        logger.info("Cartesian jog stop")
        if not was_continuous:
            return
        if (connection := self.get_active_connection()) is None:
            return logger.error("No connection found")
        connection.publisher.cartesian_move_continuous_stop()

    def _publish_cartesian_continuous(self) -> None:
        if self._cartesian is None:
            return
        if (connection := self.get_active_connection()) is None:
            return
        connection.publisher.cartesian_move_continuous_start(*self._cartesian)

    def _publish_cartesian_discrete(self) -> None:
        if self._cartesian is None:
            return
        if (connection := self.get_active_connection()) is None:
            return
        x, y, z = self._cartesian
        connection.publisher.cartesian_move_discrete(
            x * CARTESIAN_STEP,
            y * CARTESIAN_STEP,
            z * CARTESIAN_STEP,
            1000,
            3000,
        )

    def _cancel_cartesian_task(self) -> None:
        if self._cartesian_task is not None:
            self._cartesian_task.cancel()
            self._cartesian_task = None

    def _manual_publisher(self):
        if (connection := self.get_active_connection()) is None:
            logger.error("No connection found")
            return None
        if not connection.is_manual:
            logger.error(f"Active connection {connection.host} is not in manual mode")
            return None
        return connection.publisher

    def stop_all_movement(self) -> None:
        """Stops all continuous and discrete movements."""
        self.stop_joint_jog()
        self.stop_cartesian()
        if (connection := self.get_active_connection()) is None:
            return logger.error("No connection found")
        if self.control_mode == ControlMode.CONTINUOUS or self.current_continuous_directions:
            publisher = connection.publisher
            self.current_continuous_directions.clear()
            return publisher.polar_pan_continuous_stop()
        for task in self.discrete_move_task.values():
            task.cancel()
        self.discrete_move_task.clear()

    def move_home(self, hostname: str | None = None) -> None:
        """Moves the robotic arm (active connection, or `hostname`) to its home position"""
        connection = (
            self.get_active_connection()
            if hostname is None
            else self.connections.get(hostname)
        )
        if connection is None:
            return logger.error("No connection found")
        return connection.publisher.home(1000)

    def get_connection_hosts(self) -> list[str]:
        """Gets a list of all connection hostnames"""
        return list(self.connections.keys())

    def set_active_connection(self, hostname: str | None) -> Connection | None:
        """Sets the active connection by hostname"""
        logger.debug(f"Setting active connection to {hostname}")
        conn = self.connections.get_active()
        if conn is not None and hostname == conn.host:
            logger.debug(f"{hostname} is already the active connection")
            return conn
        return self.connections.set_active(hostname)

    def disconnect_connection(self, hostname: str) -> Connection | None:
        """
        Removes a connection by hostname.
        If the connection is active, sets the active connection to another available connection or None.
        """
        if (conn := self.connections.pop(hostname)) is not None:
            return conn
        logger.warning(f"Connection for hostname {hostname} not found.")

    def get_active_connection(self) -> Connection | None:
        """Gets the active connection"""
        return self.connections.get_active()

    def get_active_hostname(self) -> str | None:
        """Gets the active connection's hostname"""
        if (connection := self.get_active_connection()) is None:
            return None
        return connection.host

    def get_active_frame(self):
        """Gets the active connection's current video frame"""
        return self.streamer.get_active_frame()

    def get_active_config(self) -> ConnectionConfig | None:
        """Gets the active connection's configuration"""
        if (connection := self.get_active_connection()) is None:
            return None
        return config.ROBOT_CONFIGS.get(connection.host, None)

    def get_control_mode(self) -> ControlMode:
        """Gets the active connection's control mode"""
        return self.control_mode

    def get_director(self) -> BaseDirector | None:
        """Returns the current director"""
        return self.director

    def get_selected_model(self) -> str | None:
        """Gets the name of the currently selected model, or None if no model is selected"""
        return self.model_selection

    def change_model(self, option: str | None = None) -> bool:
        """Changes the model to the new option and starts the detection process.
        Args:
            option (str | "None" | None, optional): New model option to swap to. Defaults to None.
        """
        option = option if option != "None" else None
        if option == self.model_selection:
            return True  # No change needed
        if option is not None and len(self.connections) == 0:
            logger.warning("No connections available, skipping model initialization")
            return False
        if option is None:
            self.tracker.swap_model(None)
            self.model_selection = None
            self.streamer.draw_bboxes = self._cli_draw_bboxes
            return True
        if option not in USABLE_MODELS:
            logger.error(
                f"Model option was not found skipping initialization({option=})"
            )
            return False
        model_class = USABLE_MODELS[option]
        self.tracker.swap_model(model_class)
        logger.info(f"Initialized {option} model")
        self.model_selection = option
        self.streamer.draw_bboxes = True
        return True

    def is_manual_only(self) -> bool | None:
        """Gets the active connection's manual configuration"""
        if (connection := self.get_active_config()) is None:
            return None
        return connection.manual_only

    def get_manual_control(self, hostname: str | None = None) -> bool | None:
        """Gets the manual/automatic control mode of the active connection or `hostname`"""
        if self.director is None:
            return logger.error("No active director")
        if hostname is None:
            return self.director.get_manual_control()
        return self.director.get_manual_control(hostname=hostname)

    def set_manual_control(self, manual: bool, hostname: str | None = None) -> None:
        """Sets the manual/automatic control mode of the active connection or `hostname`"""
        if self.director is None:
            return logger.error("No active director")
        logger.debug("Setting manual control to {} for {}", manual, hostname)
        if hostname is None:
            self.director.set_manual_control(manual=manual)
            return
        self.director.set_manual_control(hostname=hostname, manual=manual)

    def set_control_mode(self, ctrl_mode: ControlMode) -> ControlMode:
        """
        Sets the control mode to the given value.
        Any ongoing movements are stopped.
        returns the new control mode
        """
        if self.control_mode == ctrl_mode:
            return self.control_mode
        self.stop_all_movement()
        self.control_mode = ctrl_mode
        return self.control_mode

    def is_director_active(self) -> bool:
        """Returns whether the director is currently active and controlling the robot"""
        if self.director is None:
            return False
        return self.director.is_active()

    def start_stream(
        self,
        streamer_type: str,
        hostname: str | None = None,
        fps: int | None = None,
        stream_config: dict[str, int | bool | str | None] = {},
    ) -> None:
        """Start streaming the active (or specified) connection.

        Raises RuntimeError when the streamer cannot open (for example, no
        virtual camera device, or no frame yet).
        """
        logger.info("Starting stream using {}", streamer_type)
        if hostname is None:
            frame_getter = self.streamer.get_active_frame  # pyright: ignore[reportAssignmentType]
            cfg = self.get_active_config()
        else:
            if hostname not in self.connections:
                raise ValueError(f"Connection to {hostname} does not exist")

            def frame_getter(host=hostname):
                return self.streamer.get_frame(host)

            cfg = config.ROBOT_CONFIGS.get(hostname)
        if cfg is None:
            return logger.error("No active connection found for streaming")
        if fps is None:
            fps = cfg.fps
        if self._streamer is not None:
            self._streamer.stop()
            self._streamer = None
        self._streamer = StreamControllerFactory.create(
            streamer_type, frame_getter, stream_config
        )
        try:
            self._streamer.start()
        except RuntimeError as exc:
            logger.error("Failed to start stream: {}", exc)
            self._streamer = None
            raise

    def stop_stream(self) -> None:
        """Stop an active ffmpeg stream if running."""
        if self._streamer is None:
            return
        self._streamer.stop()
        self._streamer = None

    def is_streaming(self) -> bool:
        return self._streamer is not None and self._streamer.is_running()

    def get_tracker_input_fps(self) -> float:
        return self.tracker.get_input_fps()

    def get_tracker_output_fps(self) -> float:
        return self.tracker.get_output_fps()
