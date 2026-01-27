from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QWidget, QLineEdit, QCheckBox,
    QGridLayout, QMessageBox
)
from PySide6.QtCore import Qt, Signal

from src.config import add_config, load_config


class QTConnectionManager(QDialog):
    """PySide6 version of connection manager"""
    connection_requested = Signal(str, int, object, bool)  # host, port, camera, write_config
    
    def __init__(self, parent, connections):
        super().__init__(parent)
        self.connections = connections
        self.setParent(parent)
        # self.parent = parent
        self.setWindowTitle("Connection Manager")
        self.setGeometry(100, 100, 350, 300)
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
        
        config = load_config()
        
        # Available configs section
        configs_label = QLabel("Available Configs:")
        configs_label.setStyleSheet("font-weight: bold;")
        self.list_layout.addWidget(configs_label)
        
        for _, cfg in config.items():
            if "socket_host" not in cfg or "socket_port" not in cfg:
                print("config missing socket_host or socket_port, skipping")
                continue
                
            row = QFrame()
            row_layout = QHBoxLayout(row)
            
            label = QLabel(f"{cfg['socket_host']} : {cfg['socket_port']}")
            row_layout.addWidget(label)
            
            connect_btn = QPushButton("Connect")
            connect_btn.clicked.connect(
                lambda checked, hostname=cfg["socket_host"]: self.add_from_config(hostname)
            )
            row_layout.addWidget(connect_btn)
            
            self.list_layout.addWidget(row)
        
        # Current connections section
        connections_label = QLabel("Current Connections:")
        connections_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        self.list_layout.addWidget(connections_label)
        
        for hostname, connData in self.connections.items():
            row = QFrame()
            row_layout = QHBoxLayout(row)
            
            label = QLabel(f"{hostname} : {connData.port}")
            row_layout.addWidget(label)
            
            remove_btn = QPushButton("X")
            remove_btn.setFixedWidth(30)
            remove_btn.clicked.connect(
                lambda checked, h=hostname: self.remove_connection(h)
            )
            row_layout.addWidget(remove_btn)
            
            self.list_layout.addWidget(row)
        
        # Add spacer at the end
        self.list_layout.addStretch()
        
    def remove_connection(self, hostname):
        if hostname in self.connections:
            # Emit signal or call parent method
            if hasattr(self.parent(), 'close_connection'):
                self.parent().close_connection(hostname)
            self.render_list()
    
    def add_connection(self, host, port, camera, write_config):
        # Emit signal to parent
        self.connection_requested.emit(host, port, camera, write_config)
        self.accept()
        
    def add_from_config(self, hostname):
        # Emit signal to parent
        if hasattr(self.parent(), 'open_connection'):
            self.parent().open_connection(hostname)
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
        
        # Save to config checkbox
        save_checkbox = QCheckBox("Save to config")
        save_checkbox.setChecked(True)
        layout.addWidget(save_checkbox)
        
        # Buttons
        button_layout = QHBoxLayout()
        submit_btn = QPushButton("Submit")
        cancel_btn = QPushButton("Cancel")
        
        submit_btn.clicked.connect(lambda: self.validate_and_submit(
            dialog, host_input.text(), port_input.text(), 
            camera_input.text(), save_checkbox.isChecked()
        ))
        cancel_btn.clicked.connect(dialog.reject)
        
        button_layout.addWidget(submit_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        dialog.exec()
        
    def validate_and_submit(self, dialog, host, port_str, camera_str, write_config):
        host = host.strip()
        port_str = port_str.strip()
        camera_str = camera_str.strip()
        
        if not host or not port_str or not camera_str:
            QMessageBox.warning(self, "Input Error", 
                              "Host, port, and camera inputs are required.")
            return
            
        try:
            port = int(port_str)
            if port < 1 or port > 65535:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Input Error", 
                              "Port must be an integer between 1 and 65535.")
            return
            
        camera = int(camera_str) if camera_str.isdigit() else camera_str
        
        self.add_connection(host, port, camera, write_config)
        dialog.accept()