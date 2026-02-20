from textual import on
from textual.containers import Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Button, Static

from src.config import ROBOT_CONFIGS
from src.talos_app import App, Connection


class ManageConnectionScreen(Screen):
    """A screen to manage connection to shared memory."""

    CSS_PATH = "connection.tcss"
    BINDINGS = [
        ("escape", "dismiss", "Close this screen"),
    ]
    current_connections: reactive[dict[str, Connection]] = reactive(dict())
    config_connections = reactive(dict())

    def __init__(self, app: App):
        super().__init__()
        self._app = app
        self.set_reactive(ManageConnectionScreen.config_connections, ROBOT_CONFIGS)
        self.set_reactive(
            ManageConnectionScreen.current_connections, self._app.get_connections()
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
        self._app.open_connection(hostname=host)
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
                Static(f"{cfg.socket_host}:{cfg.socket_port}"),
                Button(
                    "Open",
                    name=key,
                ),
            )

    async def action_dismiss_screen(self):
        return await self.dismiss(self._app.get_connections())

    def current_connections_list(self, current_connections: dict[str, Connection]):
        for key, conn in current_connections.items():
            yield Vertical(
                Static(f"{conn.host}:{conn.port}"),
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
