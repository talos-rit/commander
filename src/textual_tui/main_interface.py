from multiprocessing.managers import SharedMemoryManager

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import Button, Footer, Header, Static

from src.talos_app import App as TalosApp
from src.talos_app import Direction
from src.textual_tui.scheduler import TextualScheduler
from src.textual_tui.widgets.button import ReactiveButton
from src.textual_tui.widgets.print_viewer import PrintViewer


class Interface(App):
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
    smm: SharedMemoryManager | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(classes="column"):
                with Horizontal():
                    yield Static(id="control-selection", classes="widget")
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
                    yield Static(id="model-selection", classes="widget")
                    yield ReactiveButton("DOWN", id="down", classes="widget")
                    yield Static(id="connection-selection", classes="widget")
            yield PrintViewer(classes="column")
        yield Footer()

    def on_mount(self) -> None:
        print("Mounting Interface")
        scheduler = TextualScheduler(self)
        self._talos_app = TalosApp(scheduler, smm=self.smm)

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

    def start_mv_direction(self, direction: Direction):
        print("Start move", direction)
        self._talos_app.start_move(direction)

    def stop_mv_direction(self, direction: Direction):
        print("Stop move", direction)
        self._talos_app.stop_move(direction)


if __name__ == "__main__":
    Interface().run()
