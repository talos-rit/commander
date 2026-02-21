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
        self.connections = self.app.get_connections()
        self.setParent(parent)
        # self.parent = parent
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
        # Clear existing widgets
        for i in reversed(range(self.list_layout.count())):
            widget = self.list_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        # Available configs section
        configs_label = QLabel("Available Configs:")
        configs_label.setStyleSheet("font-weight: bold;")
        self.list_layout.addWidget(configs_label)

        for _, cfg in ROBOT_CONFIGS.items():
            config_item = QFrame()
            config_item_layout = QHBoxLayout(config_item)

            url_text = f"{cfg.socket_host}:{cfg.socket_port}"
            url_label = QLabel(url_text)
            url_label.setMaximumWidth(350)
            url_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            url_label.setToolTip(url_text)
            config_item_layout.addWidget(url_label)

            connect_btn_txt = "Connect" if cfg.socket_host not in self.connections else "Connected"
            connect_btn = QPushButton(connect_btn_txt)
            connect_btn.setEnabled(cfg.socket_host not in self.connections)
            connect_btn.clicked.connect(
                lambda _, hostname=cfg.socket_host: self.add_from_config(hostname)
            )
            config_item_layout.addWidget(connect_btn)

            self.list_layout.addWidget(config_item)

        # Current connections section
        connections_label = QLabel("Current Connections:")
        connections_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        self.list_layout.addWidget(connections_label)

        for hostname, connData in self.connections.items():
            connection_item = QFrame()
            connection_item_layout = QHBoxLayout(connection_item)
            url_text = f"{hostname}:{connData.port}"
            url_label = QLabel(url_text)
            url_label.setMaximumWidth(350)
            url_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            url_label.setToolTip(url_text)
            connection_item_layout.addWidget(url_label)

            remove_btn = QPushButton("X")
            remove_btn.setFixedWidth(30)
            remove_btn.clicked.connect(lambda _, h=hostname: self.remove_connection(h))
            connection_item_layout.addWidget(remove_btn)

            self.list_layout.addWidget(connection_item)
        # Add spacer at the end
        self.list_layout.addStretch()

    def remove_connection(self, hostname):
        if hostname in self.connections:
            # Emit signal or call parent method
            self.app.remove_connection(hostname)
            self.render_list()

    def add_connection(self, conn: ConnectionConfig):
        self.app.open_connection(conn.socket_host)
        self.update_connections.emit(conn.socket_host)
        self.accept()

    def add_from_config(self, hostname):
        self.app.open_connection(hostname)
        self.accept()

    def show_host_port_input(self):
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
            )
        )
        cancel_btn.clicked.connect(dialog.reject)

        button_layout.addWidget(submit_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        dialog.exec()

    def validate_and_submit(self, dialog, host, port_str, camera_str):
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
            return

        editor.add_config(conf)

        self.add_connection(conf)
        dialog.accept()
