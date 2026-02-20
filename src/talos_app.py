from enum import StrEnum
from multiprocessing.managers import SharedMemoryManager

from loguru import logger

from .config import CONFIG, ConnectionConfig
from .connection.connection import Connection
from .connection.publisher import Direction
from .directors import BaseDirector
from .scheduler import IterativeTask, Scheduler
from .streaming import FfmpegStreamController, StreamConfig
from .thread_scheduler import ThreadScheduler
from .tracking import USABLE_MODELS
from .tracking.tracker import Tracker


class ControlMode(StrEnum):
    CONTINUOUS = "continuous"
    DISCRETE = "discrete"


class App:
    scheduler: Scheduler
    connections: dict[str, Connection]
    _active_connection: str | None
    tracker: Tracker
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
        self.connections = dict()
        self._active_connection: None | str = None
        self.tracker = Tracker(scheduler=scheduler, smm=smm)
        self._streamer = None

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
        conf = CONFIG[hostname]
        vid_conn = self.tracker.add_capture(hostname, conf.camera_index)
        conn = Connection(hostname, conf.socket_port, vid_conn)
        self.connections[hostname] = conn
        self.set_active_connection(hostname)
        if self.director is not None and vid_conn.shape is not None:
            self.director.add_connection(conn)

    def start_move(self, direction: Direction) -> None:
        """
        Starts movement in the given direction.
        In continuous mode, starts continuous movement.
        In discrete mode, starts sending discrete movement commands at intervals.
        """
        if (connection := self.get_active_connection()) is None:
            return logger.error(f"No connection found for {self._active_connection}")
        if not connection.is_manual:
            return
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
            return logger.error(f"No connection found for {self._active_connection}")
        publisher = connection.publisher
        match direction:
            case Direction.UP:
                publisher.polar_pan_discrete(0, 10, 1000, 3000)
                logger.info("Polar pan discrete up")
            case Direction.DOWN:
                publisher.polar_pan_discrete(0, -10, 1000, 3000)
                logger.info("Polar pan discrete down")
            case Direction.LEFT:
                publisher.polar_pan_discrete(10, 0, 1000, 3000)
                logger.info("Polar pan discrete left")
            case Direction.RIGHT:
                publisher.polar_pan_discrete(-10, 0, 1000, 3000)
                logger.info("Polar pan discrete right")

    def continuous_move(self, direction: Direction) -> None:
        """
        Starts continuous movement in the given direction.
        This will merge with any existing continuous movements.
        """
        if direction in self.current_continuous_directions:
            return
        if (connection := self.get_active_connection()) is None:
            return logger.error(f"No connection found for {self._active_connection}")
        self.current_continuous_directions.add(direction)
        publisher = connection.publisher
        publisher.polar_pan_continuous_direction_start(
            sum(self.current_continuous_directions)
        )

    def stop_move(self, direction: Direction) -> None:
        """Stops continuous movement if in continuous mode and no keys are pressed."""
        if self.control_mode == ControlMode.CONTINUOUS:
            logger.info(f"{self.control_mode} {self.current_continuous_directions}")
            if direction in self.current_continuous_directions:
                self.current_continuous_directions.remove(direction)
            if len(self.current_continuous_directions) != 0:
                return
            if (connection := self.get_active_connection()) is None:
                return logger.error(f"No connection found for {self._active_connection}")
            publisher = connection.publisher
            publisher.polar_pan_continuous_stop()
            return
        if self.discrete_move_task.get(direction) is not None:
            task = self.discrete_move_task.pop(direction)
            task.cancel()

    def stop_all_movement(self) -> None:
        """Stops all continuous and discrete movements."""
        if (connection := self.get_active_connection()) is None:
            return logger.error(f"No connection found for {self._active_connection}")
        if self.control_mode == ControlMode.CONTINUOUS:
            publisher = connection.publisher
            self.current_continuous_directions.clear()
            return publisher.polar_pan_continuous_stop()
        for task in self.discrete_move_task.values():
            task.cancel()
        self.discrete_move_task.clear()

    def move_home(self) -> None:
        """Moves the robotic arm from its current location to its home position"""
        if (connectionData := self.get_active_connection()) is None:
            return logger.error(f"No connection found for {self._active_connection}")
        publisher = connectionData.publisher
        publisher.home(1000)

    def get_connections(self) -> dict[str, Connection]:
        """Gets all connections"""
        return self.connections

    def set_active_connection(self, hostname: str | None) -> None:
        """Sets the active connection by hostname"""
        logger.info(f"Setting active connection to {hostname}")
        if hostname is None:
            self.tracker.set_active_connection(None)
            self._active_connection = None
            return
        if hostname not in self.connections:
            return logger.error(f"Connection to {hostname} does not exist")
        self.tracker.set_active_connection(hostname)
        self._active_connection = hostname

    def remove_connection(self, hostname: str) -> None:
        """
        Removes a connection by hostname.
        If the connection is active, sets the active connection to another available connection or None.
        """
        if hostname not in self.connections:
            return logger.error(f"Connection to {hostname} does not exist")
        self.tracker.remove_capture(hostname)
        self.connections.pop(hostname).close()
        if self.director is not None:
            self.director.remove_control_feed(hostname)
        if hostname == self._active_connection:
            hosts = list(self.connections.keys())
            if len(hosts) > 0:
                self.set_active_connection(hosts[0])
            else:
                self.set_active_connection(None)

    def get_active_hostname(self) -> str | None:
        """Gets the active connection's hostname"""
        return self._active_connection

    def get_active_connection(self) -> Connection | None:
        """Gets the active connection"""
        if self._active_connection is None:
            return None
        return self.connections[self._active_connection]

    def get_active_frame(self):
        """Gets the active connection's current video frame"""
        if self._active_connection is None:
            return None
        return self.tracker.get_frame(self._active_connection)

    def get_frame(self, hostname: str):
        """Gets the specified connection's video frame"""
        if hostname not in self.connections:
            return None
        return self.tracker.get_frame(hostname)

    def get_active_config(self) -> dict | None:
        """Gets the active connection's configuration"""
        if self._active_connection is None:
            return None
        return CONFIG.get(self._active_connection, None)

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
            logger.info("Stopping previous model")
            self.director.stop_auto_control()
            self.director = None
        if option is None:
            return self.tracker.swap_model(None)
        if option not in USABLE_MODELS:
            return logger.error(
                f"Model option was not found skipping initialization... (found {option})"
            )
        logger.info(f"Entering {option}")
        model_class, director_class = USABLE_MODELS[option]
        self.director = director_class(self.tracker, self.connections, self.scheduler)
        self.tracker.swap_model(model_class)
        logger.info(f"Initialized {option} director")

    def is_manual_only(self) -> bool | None:
        """Gets the active connection's manual configuration"""
        if (connection := self.get_active_config()) is None:
            return None
        return connection.manual_only

    def toggle_director(self) -> None:
        """Toggles the active connection's manual/automatic control mode"""
        if (connection := self.get_active_connection()) is None:
            return logger.error(f"No connection found for {self._active_connection}")
        if self.is_manual_only():
            return logger.error(f"{connection} is set to manual only")
        connection.toggle_manual()

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
            frame_getter = self.get_active_frame
            cfg = self.get_active_config() or {}
        else:
            if hostname not in self.connections:
                raise ValueError(f"Connection to {hostname} does not exist")

            def frame_getter():
                logger.debug(f"Getting frame for {hostname}")
                return self.get_frame(hostname)

            cfg = self.config.get(hostname, {})

        if fps is None:
            fps = cfg.get("fps")

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
