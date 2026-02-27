from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
    QWidget,
    QLineEdit,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal

from loguru import logger

from src.config import ROBOT_CONFIGS, ConnectionConfig, editor
from src.talos_app import App


class QTConnectionManager(QDialog):
    """PySide6 version of connection manager"""

    update_connections = Signal(str)  # host

    def __init__(self, parent, app: App):
        super().__init__(parent)
        self.app = app
        self.connections: list[str] = []
        self._refresh_connections()
        self.setWindowTitle("Connection Manager")
        self.setGeometry(100, 100, 500, 450)
        self.setModal(True)

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Scroll area for connections list
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        self.list_layout = QVBoxLayout(scroll_widget)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        layout.addWidget(scroll_area)

        # Add button
        add_button = QPushButton("Add")
        add_button.clicked.connect(self.show_host_port_input)
        layout.addWidget(add_button)

        self.render_list()

    def render_list(self):
        self._refresh_connections()
        self._clear_list()

        configs_label = QLabel("Available Configs:")
        configs_label.setStyleSheet("font-weight: bold;")
        self.list_layout.addWidget(configs_label)

        for cfg in ROBOT_CONFIGS.values():
            self.list_layout.addWidget(self._build_config_row(cfg))

        connections_label = QLabel("Current Connections:")
        connections_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        self.list_layout.addWidget(connections_label)

        for hostname in self.connections:
            cfg = ROBOT_CONFIGS.get(hostname)
            if cfg is not None:
                self.list_layout.addWidget(self._build_connection_row(hostname, cfg.socket_port))

        self.list_layout.addStretch()

    def _refresh_connections(self) -> None:
        self.connections = list(self.app.get_connection_hosts())

    def _clear_list(self) -> None:
        for i in reversed(range(self.list_layout.count())):
            widget = self.list_layout.itemAt(i).widget()  # type: ignore
            if widget is not None:
                widget.deleteLater()

    def _build_config_row(self, cfg: ConnectionConfig) -> QFrame:
        row = QFrame()
        row_layout = QHBoxLayout(row)

        row_layout.addWidget(self._build_url_label(cfg.socket_host, cfg.socket_port))

        is_connected = cfg.socket_host in self.connections
        connect_btn = QPushButton("Connected" if is_connected else "Connect")
        connect_btn.setEnabled(not is_connected)
        connect_btn.clicked.connect(
            lambda _, hostname=cfg.socket_host: self.add_from_config(hostname)
        )
        row_layout.addWidget(connect_btn)

        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(
            lambda _, hostname=cfg.socket_host: self.show_host_port_input(hostname)
        )
        row_layout.addWidget(edit_btn)

        return row

    def _build_connection_row(self, hostname: str, port: int) -> QFrame:
        row = QFrame()
        row_layout = QHBoxLayout(row)

        row_layout.addWidget(self._build_url_label(hostname, port))

        remove_btn = QPushButton("X")
        remove_btn.setFixedWidth(30)
        remove_btn.clicked.connect(lambda _, h=hostname: self.remove_connection(h))
        row_layout.addWidget(remove_btn)

        return row

    def _build_url_label(self, hostname: str, port: int) -> QLabel:
        url_text = f"{hostname}:{port}"
        url_label = QLabel(url_text)
        url_label.setMaximumWidth(350)
        url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        url_label.setToolTip(url_text)
        return url_label

    def remove_connection(self, hostname: str):
        if hostname in self.connections:
            self.app.remove_connection(hostname)
            self._refresh_connections()
            self.render_list()

    def add_connection(self, conn: ConnectionConfig):
        self.app.open_connection(conn.socket_host)
        self.update_connections.emit(conn.socket_host)
        self.accept()

    def add_from_config(self, hostname: str):
        self.app.open_connection(hostname)
        self.update_connections.emit(hostname)
        self.accept()

    def show_host_port_input(self, robot_id=None):
        """Open a dialog to request host and port"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Enter Host and Port")
        dialog.setFixedSize(300, 300)

        layout = QVBoxLayout(dialog)

        # Host input
        host_label = QLabel("Host:")
        layout.addWidget(host_label)
        host_input = QLineEdit()
        layout.addWidget(host_input)

        # Port input
        port_label = QLabel("Port:")
        layout.addWidget(port_label)
        port_input = QLineEdit()
        layout.addWidget(port_input)

        # Camera input
        camera_label = QLabel("Camera Address:")
        layout.addWidget(camera_label)
        camera_input = QLineEdit()
        layout.addWidget(camera_input)
        
        if robot_id and robot_id in ROBOT_CONFIGS:
            host_input.setText(ROBOT_CONFIGS[robot_id].socket_host)
            port_input.setText(str(ROBOT_CONFIGS[robot_id].socket_port))
            camera_input.setText(str(ROBOT_CONFIGS[robot_id].camera_index))

        # Buttons
        button_layout = QHBoxLayout()
        submit_btn = QPushButton("Submit")
        cancel_btn = QPushButton("Cancel")

        submit_btn.clicked.connect(
            lambda: self.validate_and_submit(
                dialog,
                host_input.text(),
                port_input.text(),
                camera_input.text(),
                editing=(robot_id is not None),
            )
        )
        cancel_btn.clicked.connect(dialog.reject)

        button_layout.addWidget(submit_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        dialog.exec()

    def validate_and_submit(self, dialog, host: str, port_str: str, camera_str: str, editing=False):
        host = host.strip()
        port_str = port_str.strip()
        camera_str = camera_str.strip()

        if not host or not port_str or not camera_str:
            QMessageBox.warning(
                self, "Input Error", "Host, port, and camera inputs are required."
            )
            return

        valid, conf, error_msg = editor.validate_connection_config(
            host, port_str, camera_str
        )
        if not valid or conf is None:
            logger.warning(f"Invalid connection config: {error_msg}")
            if isinstance(error_msg, list):
                message = "\n".join(error_msg)
            else:
                message = error_msg or "Invalid connection config"
            QMessageBox.warning(self, "Input Error", message)
            return

        if editing:
            # editor.update_config(conf)
            pass
        else:
            editor.add_config(conf)
            self.add_connection(conf)
        dialog.accept()
