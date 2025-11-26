from enum import StrEnum

from .config import load_config
from .connection.connection import Connection
from .connection.publisher import Direction
from .directors import BaseDirector
from .scheduler import IterativeTask, Scheduler
from .tracking import USABLE_MODELS, Tracker


class ControlMode(StrEnum):
    CONTINUOUS = "continuous"
    DISCRETE = "discrete"


class App:
    scheduler: Scheduler
    config: dict
    connections: dict[str, Connection]
    active_connection: str | None
    tracker: Tracker
    director: BaseDirector | None = None
    control_mode: ControlMode = ControlMode.CONTINUOUS
    move_delay_ms: int = 300  # time inbetween each directional command being sent while directional button is depressed

    # State for continuous and discrete movements
    current_continuous_directions: set[Direction] = set()
    discrete_move_task: dict[Direction, IterativeTask] = dict()

    def __init__(self, scheduler: Scheduler) -> None:
        self.scheduler = scheduler
        self.config = load_config()
        self.connections = dict()
        self.active_connection: None | str = None
        self.tracker = Tracker(scheduler=scheduler)

    def open_connection(
        self,
        hostname: str,
        port: int | None = None,
        camera: int | None = None,
        write_config=False,
    ) -> None:
        if hostname in self.connections:
            return print(f"Connection to {hostname} already exists")
        conf = self.config.get(hostname, {})
        camera = conf["camera_index"] if camera is None else camera
        vid_conn = self.tracker.add_capture(hostname, camera)
        conn = Connection(hostname, port or conf["socket_port"], vid_conn)
        self.connections[hostname] = conn
        self.set_active_connection(hostname)
        if write_config:
            self.config = load_config()
        if self.director is not None and vid_conn.shape is not None:
            self.director.add_control_feed(
                hostname, conn.is_manual, vid_conn.shape, conn.publisher
            )

    def start_move(self, direction: Direction) -> None:
        if (connection := self.get_active_connection()) is None:
            return print(f"[ERROR] No connection found for {self.active_connection}")
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
        if (connection := self.get_active_connection()) is None:
            return print(f"[ERROR] No connection found for {self.active_connection}")
        publisher = connection.publisher
        match direction:
            case Direction.UP:
                publisher.polar_pan_discrete(0, 10, 1000, 3000)
                print("Polar pan discrete up")
            case Direction.DOWN:
                publisher.polar_pan_discrete(0, -10, 1000, 3000)
                print("Polar pan discrete down")
            case Direction.LEFT:
                publisher.polar_pan_discrete(10, 0, 1000, 3000)
                print("Polar pan discrete left")
            case Direction.RIGHT:
                publisher.polar_pan_discrete(-10, 0, 1000, 3000)
                print("Polar pan discrete right")

    def continuous_move(self, direction: Direction) -> None:
        if direction in self.current_continuous_directions:
            return
        if (connection := self.get_active_connection()) is None:
            return print(f"[ERROR] No connection found for {self.active_connection}")
        self.current_continuous_directions.add(direction)
        publisher = connection.publisher
        publisher.polar_pan_continuous_direction_start(
            sum(self.current_continuous_directions)
        )

    def stop_move(self, direction: Direction) -> None:
        """Stops continuous movement if in continuous mode and no keys are pressed."""
        if self.control_mode == ControlMode.CONTINUOUS:
            print(self.control_mode, self.current_continuous_directions)
            if direction in self.current_continuous_directions:
                self.current_continuous_directions.remove(direction)
            if len(self.current_continuous_directions) != 0:
                return
            if (connection := self.get_active_connection()) is None:
                return print(
                    f"[ERROR] No connection found for {self.active_connection}"
                )
            publisher = connection.publisher
            publisher.polar_pan_continuous_stop()
            return
        print(self.control_mode, self.discrete_move_task)
        if self.discrete_move_task.get(direction) is not None:
            task = self.discrete_move_task.pop(direction)
            task.cancel()

    def move_home(self) -> None:
        """Moves the robotic arm from its current location to its home position"""
        if (connectionData := self.get_active_connection()) is None:
            return print(f"[ERROR] No connection found for {self.active_connection}")
        publisher = connectionData.publisher
        publisher.home(1000)

    def get_connections(self) -> dict[str, Connection]:
        return self.connections

    def set_active_connection(self, hostname: str | None) -> None:
        if hostname is None:
            self.tracker.set_active_connection(None)
            self.active_connection = None
            return
        if hostname not in self.connections:
            return print(f"[ERROR] Connection to {hostname} does not exist")
        self.tracker.set_active_connection(hostname)
        self.active_connection = hostname

    def remove_connection(self, hostname: str) -> None:
        if hostname not in self.connections:
            return print(f"[ERROR] Connection to {hostname} does not exist")
        if hostname == self.active_connection:
            hosts = list(self.connections.keys())
            print(hosts)
            if len(hosts) > 1:
                self.set_active_connection(hosts[0])
            else:
                self.set_active_connection(None)
        self.tracker.remove_capture(hostname)
        self.connections.pop(hostname).close()
        if self.director is not None:
            self.director.remove_control_feed(hostname)

    def get_active_connection(self) -> Connection | None:
        if self.active_connection is None:
            return None
        return self.connections[self.active_connection]

    def get_active_frame(self):
        if self.active_connection is None:
            return None
        return self.tracker.get_frame(self.active_connection)

    def get_active_config(self) -> dict | None:
        if self.active_connection is None:
            return None
        return self.config.get(self.active_connection, None)

    def get_control_mode(self) -> ControlMode:
        """Gets the active connection's control mode"""
        return self.control_mode

    def get_director(self) -> BaseDirector | None:
        return self.director

    def change_model(self, option: str | None = None) -> None:
        option = option if option != "None" else None
        if self.director is not None:
            print("Stopping previous model")
            self.director.stop_auto_control()
            self.director = None
        if option is None:
            return self.tracker.swap_model(None)
        if option not in USABLE_MODELS:
            return print(
                f"Model option was not found skipping initialization... (found {option})"
            )
        print(f"Entering {option}")
        model_class, director_class = USABLE_MODELS[option]
        self.director = director_class(self.tracker, self.connections, self.scheduler)
        self.tracker.swap_model(model_class)
        print(f"Initialized {option} director")

    def is_manual_only(self) -> bool:
        """Gets the active connection's manual configuration"""
        if (connection := self.get_active_connection()) is None:
            return False
        return connection.is_manual_only

    def toggle_director(self) -> None:
        """Toggles the active connection's manual/automatic control mode"""
        if (connection := self.get_active_connection()) is None:
            return print(f"[ERROR] No connection found for {self.active_connection}")
        if self.is_manual_only():
            return print(f"[ERROR] {connection} is set to manual only")
        connection.toggle_manual()
        if self.director is not None:
            self.director.update_control_feed(connection.host, connection.is_manual)

    def toggle_control_mode(self) -> None:
        """Toggles between continuous and discrete control modes"""
        if self.control_mode == ControlMode.CONTINUOUS:
            self.control_mode = ControlMode.DISCRETE
        else:
            self.control_mode = ControlMode.CONTINUOUS
