from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Static

from src.textual_tui.widgets.print_viewer import PrintViewer


class Interface(App):
    CSS_PATH = "app.tcss"
    BINDINGS = [("q", "quit", "Quit")]

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
        print("Hello from print()!")
        print("Another line...")

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


if __name__ == "__main__":
    Interface().run()
