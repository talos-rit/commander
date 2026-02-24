from textual import on
from textual.containers import Vertical
from textual.events import Mount
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Button, Header, Input, SelectionList

from src.config import ROBOT_CONFIGS, editor
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
        self.set_reactive(ManageConnectionScreen.config_connections, ROBOT_CONFIGS)
        self.set_reactive(
            ManageConnectionScreen.current_connections, self._app.get_connection_hosts()
        )

    def compose(self):
        with Vertical():
            yield Header()
            selections = SelectionList[str](
                *self.connections_list(self.config_connections),
                id="previous-connections-list",
                classes="prev-connections-list",
            )
            selections.border_title = "Previous Connections"
            yield selections
            form = Vertical(id="form-container")
            form.border_title = "Add New Connection"
            with form:
                yield Input(placeholder="hostname:port", id="operator-url-input")
                yield Input(placeholder="Camera source", id="camera-source-input")
                yield Button("Add New Connection", id="add-connection-btn")

    @on(Mount)
    def on_mount(self):
        self.title = "Manage Connections"
        self.set_focus(self.query_one("#previous-connections-list", SelectionList))

    @on(SelectionList.SelectedChanged)
    def handle_active_connection(self):
        selected = self.query_one("#previous-connections-list", SelectionList).selected
        current_connections = self._app.get_connection_hosts()
        for conn in current_connections:
            if conn not in selected:
                self._app.remove_connection(conn)
                self.current_connections.remove(conn)
        for conn in selected:
            if conn not in current_connections:
                self._app.open_connection(hostname=conn)
                self.current_connections.append(conn)

    def connections_list(self, config_connections: dict) -> list[tuple[str, str, bool]]:
        if self._app is None:
            return []
        selection_list = []
        curr_hostnames = self._app.get_connection_hosts()
        for key, cfg in config_connections.items():
            selection_list.append(
                (f"{cfg.socket_host}:{cfg.socket_port}", key, key in curr_hostnames)
            )
        return selection_list

    async def action_dismiss_screen(self):
        return await self.dismiss(self._app.get_connection_hosts())

    @on(Button.Pressed, "#add-connection-btn")
    def handle_add_connection(self, event: Button.Pressed):
        operator_url = self.query_one("#operator-url-input", Input)
        camera_src = self.query_one("#camera-source-input", Input)
        try:
            hostname, port = operator_url.value.strip().split(":")
            port = int(port)
        except Exception:
            self.notify("Invalid operator URL. Please use the format hostname:port")
            return
        camera = camera_src.value.strip()
        valid, conf, error_msg = editor.validate_connection_config(
            hostname, port, camera
        )
        if not valid:
            self.notify(f"Invalid connection config: {error_msg}")
            return
        if conf is None:
            self.notify("Invalid connection config: Unknown error")
            return
        editor.add_config(conf)
        self._app.open_connection(conf.socket_host)
        self.current_connections.append(conf.socket_host)
        self.notify(f"Added new connection: {conf.socket_host}:{conf.socket_port}")
        self.clear_input_fields()
        self.add_option_to_selection_list(
            (f"{conf.socket_host}:{conf.socket_port}", conf.socket_host, True)
        )

    def clear_input_fields(self):
        self.query_one("#operator-url-input", Input).value = ""
        self.query_one("#camera-source-input", Input).value = ""

    def add_option_to_selection_list(self, new_option: tuple[str, str, bool]):
        selections = self.query_one("#previous-connections-list", SelectionList)
        selections.add_option(new_option)
