from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Static

from src.talos_app import App as TalosApp
from src.talos_app import Direction
from src.textual_tui.scheduler import TextualScheduler
from src.textual_tui.widgets.print_viewer import PrintViewer


class Interface(App):
    CSS_PATH = "app.tcss"
    BINDINGS = [("q", "quit", "Quit")]
    _talos_app: TalosApp

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(classes="column"):
                with Horizontal():
                    yield Static(id="control-selection", classes="widget")
                    yield Button("UP", classes="widget", action="app.key_up()")
                    yield Static(id="placeholder", classes="widget")
                with Horizontal():
                    yield Button("LEFT", classes="widget", action="app.key_left()")
                    yield Button("HOME", classes="widget", action="app.key_space()")
                    yield Button("RIGHT", classes="widget", action="app.key_right()")
                with Horizontal():
                    yield Static(id="model-selection", classes="widget")
                    yield Button("DOWN", classes="widget", action="app.key_down()")
                    yield Static(id="connection-selection", classes="widget")
            yield PrintViewer(classes="column")
        yield Footer()

    def on_mount(self) -> None:
        scheduler = TextualScheduler(self)
        self._talos_app = TalosApp(scheduler)

    async def key_up(self) -> None:
        await self.run_action("key_up")

    async def key_left(self) -> None:
        await self.run_action("key_left")

    async def key_right(self) -> None:
        await self.run_action("key_right")

    async def key_down(self) -> None:
        await self.run_action("key_down")

    async def key_space(self) -> None:
        await self.run_action("key_space")

    def action_key_up(self) -> None:
        print("UP button pressed")

    def action_key_left(self) -> None:
        print("LEFT button pressed")

    def action_key_right(self) -> None:
        print("RIGHT button pressed")

    def action_key_down(self) -> None:
        print("DOWN button pressed")

    def action_key_space(self) -> None:
        print("HOME button pressed")
        self._talos_app.move_home()

    def mv_direction(self, direction: Direction):
        self._talos_app.start_move(direction)


if __name__ == "__main__":
    Interface().run()
