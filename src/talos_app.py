from enum import StrEnum
from multiprocessing.managers import SharedMemoryManager

from loguru import logger

from .config import ROBOT_CONFIGS, ConnectionConfig
from .connection.connection import Connection, ConnectionCollection, VideoConnection
from .connection.publisher import Direction
from .directors import BaseDirector, ContinuousDirector
from .scheduler import IterativeTask, Scheduler
from .streaming import FfmpegStreamController, StreamConfig
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


class App:
    scheduler: Scheduler
    connections: ConnectionCollection
    tracker: Tracker
    streamer: Streamer
    director: BaseDirector | None = None
    control_mode: ControlMode = ControlMode.CONTINUOUS
    move_delay_ms: int = 300  # time inbetween each directional command being sent while directional button is depressed

    # State for continuous and discrete movements
    current_continuous_directions: set[Direction] = set()
    discrete_move_task: dict[Direction, IterativeTask] = dict()
    _streamer: FfmpegStreamController | None = None

    def __init__(
        self,
        scheduler: Scheduler = ThreadScheduler(),
        smm: SharedMemoryManager = SharedMemoryManager(),
    ) -> None:
        self.scheduler = scheduler
        self.connections = ConnectionCollection()
        self.tracker = Tracker(self.connections, scheduler=scheduler, smm=smm)
        self.streamer = Streamer(self.connections, draw_bboxes=True)
        self.director = ContinuousDirector(
            self.tracker, self.connections, self.scheduler
        )

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
        conf = ROBOT_CONFIGS[hostname]
        video_connection = VideoConnection(src=conf.camera_index)
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
            logger.debug(f"{self.control_mode} {self.current_continuous_directions}")
            if direction in self.current_continuous_directions:
                self.current_continuous_directions.remove(direction)
            if len(self.current_continuous_directions) != 0:
                return
            if (connection := self.get_active_connection()) is None:
                return logger.error("No connection found")
            return connection.publisher.polar_pan_continuous_stop()
        if self.discrete_move_task.get(direction) is not None:
            return self.discrete_move_task.pop(direction).cancel()

    def stop_all_movement(self) -> None:
        """Stops all continuous and discrete movements."""
        if (connection := self.get_active_connection()) is None:
            return logger.error("No connection found")
        if self.control_mode == ControlMode.CONTINUOUS:
            publisher = connection.publisher
            self.current_continuous_directions.clear()
            return publisher.polar_pan_continuous_stop()
        for task in self.discrete_move_task.values():
            task.cancel()
        self.discrete_move_task.clear()

    def move_home(self) -> None:
        """Moves the robotic arm from its current location to its home position"""
        if (connection := self.get_active_connection()) is None:
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

    def remove_connection(self, hostname: str) -> Connection | None:
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
        return ROBOT_CONFIGS.get(connection.host, None)

    def get_control_mode(self) -> ControlMode:
        """Gets the active connection's control mode"""
        return self.control_mode

    def get_director(self) -> BaseDirector | None:
        """Returns the current director"""
        return self.director

    def change_model(self, option: str | None = None) -> None:
        """Changes the model to the new option and starts the detection process.
        Args:
            option (str | "None" | None, optional): New model option to swap to. Defaults to None.
        """
        option = option if option != "None" else None
        if self.director is not None:
            self.director.stop_auto_control()
            logger.info("Director stopped")
        if option is None:
            return self.tracker.swap_model(None)
        if option not in USABLE_MODELS:
            return logger.error(
                f"Model option was not found skipping initialization({option=})"
            )
        model_class = USABLE_MODELS[option]
        self.tracker.swap_model(model_class)
        logger.info(f"Initialized {option} model")

    def is_manual_only(self) -> bool | None:
        """Gets the active connection's manual configuration"""
        if (connection := self.get_active_config()) is None:
            return None
        return connection.manual_only

    def toggle_director(self) -> None:
        """Toggles the active connection's manual/automatic control mode"""
        if self.director is None:
            return logger.error("No active director")
        self.director.toggle_control_mode()

    def toggle_control_mode(self) -> ControlMode:
        """
        Toggles between continuous and discrete control.
        Any ongoing movements are stopped.
        returns the new control mode
        """
        self.stop_all_movement()
        self.control_mode = (
            ControlMode.DISCRETE
            if self.control_mode == ControlMode.CONTINUOUS
            else ControlMode.CONTINUOUS
        )
        return self.control_mode

    def is_director_active(self) -> bool:
        """Returns whether the director is currently active and controlling the robot"""
        if self.director is None:
            return False
        return self.director.is_active()

    def start_stream(
        self,
        output_url: str,
        hostname: str | None = None,
        fps: int | None = None,
        use_docker: bool = False,
        docker_image: str | None = None,
        docker_network: str | None = None,
    ) -> None:
        """Start streaming the active (or specified) connection via ffmpeg."""
        logger.info("Starting stream to {}", output_url)
        if hostname is None:
            frame_getter = self.streamer.get_active_frame  # pyright: ignore[reportAssignmentType]
            cfg = self.get_active_config()
        else:
            if hostname not in self.connections:
                raise ValueError(f"Connection to {hostname} does not exist")

            def frame_getter(host=hostname):
                return self.streamer.get_frame(host)

            cfg = ROBOT_CONFIGS.get(hostname)
        if cfg is None:
            return logger.error("No active connection found for streaming")
        if fps is None:
            fps = cfg.fps
        if self._streamer is not None:
            self._streamer.stop()
            self._streamer = None
        stream_config = StreamConfig(
            output_url=output_url,
            fps=fps,
            use_docker=use_docker,
            docker_image=docker_image or StreamConfig.docker_image,
            docker_network=docker_network,
        )
        self._streamer = FfmpegStreamController(frame_getter, stream_config)
        try:
            self._streamer.start()
        except RuntimeError as exc:
            logger.error("Failed to start stream: {}", exc)
            self._streamer = None

    def stop_stream(self) -> None:
        """Stop an active ffmpeg stream if running."""
        if self._streamer is None:
            return
        self._streamer.stop()
        self._streamer = None

    def is_streaming(self) -> bool:
        return self._streamer is not None and self._streamer.is_running()
