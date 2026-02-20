from textual import on
from textual.containers import Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Button, Static

from src.config import load_config
from src.talos_app import App


class ManageConnectionScreen(Screen):
    """A screen to manage connection to shared memory."""

    CSS_PATH = "connection.tcss"
    BINDINGS = [
        ("escape", "dismiss", "Close this screen"),
    ]
    current_connections: reactive[list[str]] = reactive(list())
    config_connections = reactive(dict())
    _app: App

    def __init__(self, app: App):
        super().__init__()
        self._app = app
        self.set_reactive(ManageConnectionScreen.config_connections, load_config())
        self.set_reactive(
            ManageConnectionScreen.current_connections, self._app.get_connection_hosts()
        )

    def compose(self):
        yield Static("Configured Connections", classes="section-header")
        with Vertical(
            id="previous-connections-list",
            classes="prev-connections-list",
        ):
            yield from self.previous_connections_list(self.config_connections)
        yield Static("Open Connections", classes="section-header")
        with Vertical(
            id="current-connections-list",
            classes="current-connections-list",
        ):
            yield from self.current_connections_list(self.current_connections)

    @on(Button.Pressed, "#previous-connections-list Button")
    def action_open_connection(self, e: Button.Pressed):
        host = e.button.name
        if self._app is None or host is None:
            return
        config = self.config_connections[host]
        self._app.open_connection(
            hostname=host,
            port=config["socket_port"],
            camera=config["camera_index"],
            write_config=False,
        )
        self.mutate_reactive(ManageConnectionScreen.current_connections)

    @on(Button.Pressed, "#current-connections-list Button")
    def action_close_connection(self, hostname):
        if self._app is None:
            return
        self._app.remove_connection(hostname)

    def previous_connections_list(self, config_connections: dict):
        if self._app is None:
            return None

        for key, cfg in config_connections.items():
            yield Vertical(
                Static(f"{cfg['socket_host']}:{cfg['socket_port']}"),
                Button(
                    "Open",
                    name=key,
                ),
            )

    async def action_dismiss_screen(self):
        return await self.dismiss(self._app.get_connection_hosts())

    def current_connections_list(self, current_connections: list[str]):
        for key in current_connections:
            yield Vertical(
                Static(f"{key}"),
                Button("Close", name=key),
            )

    def watch_config_connections(self, config_connections):
        previous_list = self.query_one("#previous-connections-list")
        previous_list.remove_children()
        for child in list(self.previous_connections_list(config_connections)):
            previous_list.mount(child)

    def watch_current_connections(self, current_connections):
        current_list = self.query_one("#current-connections-list")
        current_list.remove_children()
        for child in list(self.current_connections_list(current_connections)):
            current_list.mount(child)
