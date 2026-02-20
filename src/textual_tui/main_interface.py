from multiprocessing.managers import SharedMemoryManager

from loguru import logger
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.timer import Timer
from textual.widgets import Button, Footer, Header, Select, Static, Switch

from src.talos_app import App as TalosApp
from src.talos_app import ControlMode, Direction
from src.textual_tui.manage_connection import ManageConnectionScreen
from src.textual_tui.scheduler import TextualScheduler
from src.textual_tui.widgets.button import ReactiveButton
from src.textual_tui.widgets.print_viewer import PrintViewer
from src.tracking import MODEL_OPTIONS

from ..talos_endpoint import TalosEndpoint
from ..tk_gui.main_interface import start_termination_guard
from ..utils import terminate

MODEL_OPTIONS_TEXTUAL = list((e, e) for e in MODEL_OPTIONS)


class TextualInterface(App):
    CSS_PATH = "app.tcss"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("space", "home", "Home"),
        ("up", "mv_up", "Up"),
        ("down", "mv_down", "Down"),
        ("left", "mv_left", "Left"),
        ("right", "mv_right", "Right"),
    ]
    _talos_app: TalosApp
    debounce_timers: dict[str, Timer] = dict()
    smm: SharedMemoryManager = SharedMemoryManager()
    connection_options = reactive([("None", None)])

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(classes="column"):
                with Horizontal():
                    with Vertical(classes="widget"):
                        yield Static("Control Mode:", classes="label-text")
                        yield Switch(value=False, id="auto-mode-switch")
                        yield Static("Continuous Control:", classes="label-text")
                        yield Switch(value=False, id="continuous-control-switch")
                    yield ReactiveButton("UP", id="up", classes="widget")
                    yield Static(id="placeholder", classes="widget")
                with Horizontal():
                    yield ReactiveButton("LEFT", id="left", classes="widget")
                    yield Button(
                        "HOME",
                        id="home",
                        classes="widget",
                        action="app.home()",
                    )
                    yield ReactiveButton("RIGHT", id="right", classes="widget")
                with Horizontal():
                    with Vertical(classes="widget"):
                        yield Static("Model:", classes="label-text")
                        yield Select(MODEL_OPTIONS_TEXTUAL, id="model-select")
                    yield ReactiveButton("DOWN", id="down", classes="widget")
                    with Vertical(classes="widget connection-widget"):
                        yield Button(
                            "Manage Connection",
                            id="manage-connection",
                            classes="manage-connection",
                            action="app.manage_connection()",
                        )
                        yield Select(
                            self.connection_options,
                            id="connection-select",
                        )
            yield PrintViewer(classes="column")
        yield Footer()

    def watch_connection_options(self, old_options, new_options):
        """This function runs automatically when self.connection_options changes"""
        if len(old_options) == len(new_options) and all(
            o == n for o, n in zip(old_options, new_options)
        ):
            return
        self.query_one("#connection-select", Select).set_options(new_options)

    def run_server(self):
        endpoint = TalosEndpoint(self._talos_app)
        endpoint.run()

    def on_mount(self) -> None:
        logger.debug("Mounting Interface")
        scheduler = TextualScheduler(self)
        self._talos_app = TalosApp(scheduler, smm=self.smm)
        self.run_server()

        start_termination_guard()

        continuous_switch = self.query_one("#continuous-control-switch", Switch)
        continuous_switch.value = (
            self._talos_app.get_control_mode() == ControlMode.CONTINUOUS
        )

    @on(ReactiveButton.Active, "#up")
    def action_up(self):
        self.start_mv_direction(Direction.UP)

    @on(ReactiveButton.Active, "#left")
    def action_left(self):
        self.start_mv_direction(Direction.LEFT)

    @on(ReactiveButton.Active, "#right")
    def action_right(self):
        self.start_mv_direction(Direction.RIGHT)

    @on(ReactiveButton.Active, "#down")
    def action_down(self):
        self.start_mv_direction(Direction.DOWN)

    @on(ReactiveButton.Released, "#up")
    def action_up_end(self):
        self.stop_mv_direction(Direction.UP)

    @on(ReactiveButton.Released, "#left")
    def action_left_end(self):
        self.stop_mv_direction(Direction.LEFT)

    @on(ReactiveButton.Released, "#right")
    def action_right_end(self):
        self.stop_mv_direction(Direction.RIGHT)

    @on(ReactiveButton.Released, "#down")
    def action_down_end(self):
        self.stop_mv_direction(Direction.DOWN)

    @on(Select.Changed, "#model-select")
    def model_changed(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK:
            return self._talos_app.change_model(None)
        self._talos_app.change_model(str(event.value))

    @on(Switch.Changed, "#auto-mode-switch")
    def auto_mode_changed(self, _: Switch.Changed) -> None:
        self._talos_app.toggle_director()

    @on(Switch.Changed, "#continuous-control-switch")
    def continuous_control_changed(self, _: Switch.Changed) -> None:
        self._talos_app.toggle_control_mode()

    def debounce_input(self, name, func, wait_ms: int = 100):
        def called():
            del self.debounce_timers[name]
            func()

        if name not in self.debounce_timers:
            self.debounce_timers[name] = self.set_timer(
                wait_ms / 1000,
                called,
            )
            return
        timer = self.debounce_timers[name]
        timer.reset()

    def action_home(self):
        self._talos_app.move_home()

    def key_w(self):
        self.action_mv_up()

    def action_mv_up(self):
        self.start_mv_direction(Direction.UP)
        self.debounce_input(
            "up",
            lambda: self.stop_mv_direction(Direction.UP),
        )

    def key_a(self):
        self.action_mv_left()

    def action_mv_left(self):
        self.start_mv_direction(Direction.LEFT)
        self.debounce_input(
            "left",
            lambda: self.stop_mv_direction(Direction.LEFT),
        )

    def key_s(self):
        self.action_mv_down()

    def action_mv_down(self):
        self.start_mv_direction(Direction.DOWN)
        self.debounce_input(
            "down",
            lambda: self.stop_mv_direction(Direction.DOWN),
        )

    def key_d(self):
        self.action_mv_right()

    def action_mv_right(self):
        self.start_mv_direction(Direction.RIGHT)
        self.debounce_input(
            "right",
            lambda: self.stop_mv_direction(Direction.RIGHT),
        )

    @work
    async def action_manage_connection(self):
        await self.push_screen(
            ManageConnectionScreen(self._talos_app), wait_for_dismiss=True
        )

        connections = [
            (conn, conn) for conn in self._talos_app.get_connections().keys()
        ]
        self.connection_options = connections
        self.query_one("#connection-select", Select).value = (
            self._talos_app._active_connection or Select.BLANK
        )

    @on(Select.Changed, "#connection-select")
    def handle_active_connection(self, active_connection: Select.Changed):
        logger.info(f"Active connection changed to: {active_connection.value}")
        if not hasattr(self, "_talos_app"):
            return
        new_connection = str(active_connection.value)
        self._talos_app.set_active_connection(new_connection)

    def start_mv_direction(self, direction: Direction):
        logger.info(f"Start move {direction}")
        self._talos_app.start_move(direction)

    def stop_mv_direction(self, direction: Direction):
        logger.info(f"Stop move {direction}")
        self._talos_app.stop_move(direction)

    def get_app(self) -> TalosApp:
        return self._talos_app


if __name__ == "__main__":
    try:
        TextualInterface().run()
    finally:
        terminate(0, 0)
