import sys
from enum import StrEnum
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QFrame, QComboBox, QCheckBox,
    QScrollArea, QSizePolicy, QDialog
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QThread
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QFont, QKeyEvent
import cv2
import numpy as np

from src.config import load_default_config
from src.connection.publisher import Direction
from src.talos_app import App, ControlMode
from src.pyside_gui.connection_manager import QTConnectionManager
from src.pyside_gui.styles import get_main_stylesheet, COLORS
from src.pyside_gui.qtscheduler import QTScheduler
from src.tracking import MODEL_OPTIONS
from src.utils import (
    add_termination_handler,
    remove_termination_handler,
    start_termination_guard,
    terminate,
)

from loguru import logger


class VideoThread(QThread):
    """Thread for processing video frames"""
    frame_processed = Signal(np.ndarray)
    
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.running = True
        
    def run(self):
        while self.running:
            frame = self.app.get_active_frame()
            if frame is not None:
                self.frame_processed.emit(frame)
            self.msleep(50)  # ~20 FPS
    
    def stop(self):
        self.running = False
        self.wait()


class ButtonText(StrEnum):
    """Button text Enum for interface controls"""
    UP = "↑"
    DOWN = "↓"
    LEFT = "←"
    RIGHT = "→"
    HOME = "🏠 Home"
    CONTINUOUS_MODE_LABEL = "Continuous"
    AUTOMATIC_MODE_LABEL = "Automatic"


DIRECTIONAL_KEY_BINDING_MAPPING = {
    Qt.Key.Key_Up: Direction.UP,
    Qt.Key.Key_Down: Direction.DOWN,
    Qt.Key.Key_Left: Direction.LEFT,
    Qt.Key.Key_Right: Direction.RIGHT,
}


class PySide6Interface(QMainWindow):
    """
    PySide6 version of the manual interface for controlling
    the robotic arm which holds the camera.
    """
    
    # Signals
    connection_changed = Signal(str, object, object, bool)  # host, port, camera, write_config
    
    def __init__(self) -> None:
        """Constructor sets up PySide6 manual interface"""
        super().__init__()
        
        start_termination_guard()
        self._term = add_termination_handler(self.close)
        
        self.setWindowTitle("Talos Manual Interface")
        self.setGeometry(100, 100, 900, 700)
        
        # Set application style
        self.setStyleSheet(get_main_stylesheet())
        
        self.scheduler = QTScheduler()
        self.app = App(self.scheduler)
        self.default_config = load_default_config()
        
        # Video thread
        self.video_thread = VideoThread(self.app)
        self.video_thread.frame_processed.connect(self.update_video_frame)
        
        # Setup UI
        self.setup_ui()
        
        # Setup keyboard controls
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # Initial UI state
        self.set_manual_control_btn_state(False)
        
    def setup_ui(self):
        """Setup the main UI layout"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QGridLayout(central_widget)
        main_layout.setRowStretch(0, 3)  # Video row gets 3x weight
        main_layout.setRowStretch(1, 1)
        main_layout.setRowStretch(2, 1)
        main_layout.setRowStretch(3, 1)
        
        # Video display
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setMinimumSize(500, 380)
        self.video_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_label.setStyleSheet("border: 2px solid gray; background-color: black;")
        main_layout.addWidget(self.video_label, 0, 0, 1, 3)
        
        # Create "No Signal" display
        self.draw_no_signal_display()
        
        # Toggle group frame
        toggle_frame = QFrame()
        toggle_layout = QVBoxLayout(toggle_frame)
        
        # Automatic mode toggle
        self.automatic_button = QCheckBox(ButtonText.AUTOMATIC_MODE_LABEL)
        self.automatic_button.setFont(QFont("Cascadia Code", 12, QFont.Weight.Bold))
        self.automatic_button.toggled.connect(self.toggle_command_mode)
        self.automatic_button.setEnabled(False)
        toggle_layout.addWidget(self.automatic_button)
        
        # Continuous mode toggle
        self.continuous_button = QCheckBox(ButtonText.CONTINUOUS_MODE_LABEL)
        self.continuous_button.setFont(QFont("Cascadia Code", 12, QFont.Weight.Bold))
        self.continuous_button.toggled.connect(self.app.toggle_control_mode)
        toggle_layout.addWidget(self.continuous_button)
        
        main_layout.addWidget(toggle_frame, 1, 0)
        
        # Directional controls
        # Home button
        self.home_button = QPushButton(ButtonText.HOME)
        self.home_button.setFont(QFont("Cascadia Code", 16, QFont.Weight.Bold))
        self.home_button.clicked.connect(self.app.move_home)
        main_layout.addWidget(self.home_button, 2, 1)
        
        # Directional buttons
        self.up_button = QPushButton(ButtonText.UP)
        self.up_button.setFont(QFont("Cascadia Code", 16, QFont.Weight.Bold))
        self.up_button.pressed.connect(lambda: self.app.start_move(Direction.UP))
        self.up_button.released.connect(lambda: self.app.stop_move(Direction.UP))
        main_layout.addWidget(self.up_button, 1, 1)
        
        self.down_button = QPushButton(ButtonText.DOWN)
        self.down_button.setFont(QFont("Cascadia Code", 16, QFont.Weight.Bold))
        self.down_button.pressed.connect(lambda: self.app.start_move(Direction.DOWN))
        self.down_button.released.connect(lambda: self.app.stop_move(Direction.DOWN))
        main_layout.addWidget(self.down_button, 3, 1)
        
        self.left_button = QPushButton(ButtonText.LEFT)
        self.left_button.setFont(QFont("Cascadia Code", 16, QFont.Weight.Bold))
        self.left_button.pressed.connect(lambda: self.app.start_move(Direction.LEFT))
        self.left_button.released.connect(lambda: self.app.stop_move(Direction.LEFT))
        main_layout.addWidget(self.left_button, 2, 0)
        
        self.right_button = QPushButton(ButtonText.RIGHT)
        self.right_button.setFont(QFont("Cascadia Code", 16, QFont.Weight.Bold))
        self.right_button.pressed.connect(lambda: self.app.start_move(Direction.RIGHT))
        self.right_button.released.connect(lambda: self.app.stop_move(Direction.RIGHT))
        main_layout.addWidget(self.right_button, 2, 2)
        
        # Model selection frame
        model_frame = QFrame()
        model_layout = QVBoxLayout(model_frame)
        
        model_label = QLabel("Detection Model")
        model_label.setFont(QFont("Cascadia Code", 12))
        model_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        model_layout.addWidget(model_label)
        
        self.model_combo = QComboBox()
        self.model_combo.addItem("None")
        self.model_combo.addItems(MODEL_OPTIONS)
        self.model_combo.currentTextChanged.connect(self.change_model)
        model_layout.addWidget(self.model_combo)
        
        main_layout.addWidget(model_frame, 3, 0)
        
        # Connection management frame
        connection_frame = QFrame()
        connection_layout = QVBoxLayout(connection_frame)
        
        self.manage_connections_btn = QPushButton("Manage connections")
        self.manage_connections_btn.clicked.connect(self.manage_connections)
        connection_layout.addWidget(self.manage_connections_btn)
        
        self.connection_combo = QComboBox()
        self.connection_combo.currentTextChanged.connect(lambda option: self.set_active_connection(option))
        connection_layout.addWidget(self.connection_combo)
        
        main_layout.addWidget(connection_frame, 3, 2)
        
        # Connect signals
        self.connection_changed.connect(self.open_connection)
        
        self.update_ui()
        
    def keyPressEvent(self, event: QKeyEvent):
        """Handle key press events for directional controls"""
        key = Qt.Key(event.key())
        if key in DIRECTIONAL_KEY_BINDING_MAPPING:
            direction = DIRECTIONAL_KEY_BINDING_MAPPING[key]
            self.app.start_move(direction)
        else:
            super().keyPressEvent(event)
    
    def keyReleaseEvent(self, event: QKeyEvent):
        """Handle key release events for directional controls"""
        key = Qt.Key(event.key())
        if key in DIRECTIONAL_KEY_BINDING_MAPPING:
            direction = DIRECTIONAL_KEY_BINDING_MAPPING[key]
            self.app.stop_move(direction)
        else:
            super().keyReleaseEvent(event)
    
    def draw_no_signal_display(self):
        """Create and display 'No Signal' image"""
        pixmap = QPixmap(500, 380)
        pixmap.fill(QColor("gray"))
        
        painter = QPainter(pixmap)
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Arial", 24))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "No Signal")
        painter.end()
        
        self.video_label.setPixmap(pixmap)
    
    def update_video_frame(self, frame):
        """Update the video display with new frame"""
        if frame is None:
            return
            
        config_data = self.app.get_active_config() or self.default_config
        desired_height = config_data.get("frame_height")
        desired_width = config_data.get("frame_width")
        
        # Convert BGR to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_frame.shape
        bytes_per_line = ch * w
        
        # Create QImage from numpy array
        qimage = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        
        # Resize if needed
        if desired_width and desired_height:
            qimage = qimage.scaled(desired_width, desired_height, 
                                  Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        elif desired_width:
            qimage = qimage.scaledToWidth(desired_width, Qt.TransformationMode.SmoothTransformation)
        
        # Convert to QPixmap and display
        pixmap = QPixmap.fromImage(qimage)
        self.video_label.setPixmap(pixmap)
    
    def open_connection(self, hostname, port=None, camera=None, write_config=False):
        """Open a new connection"""
        self.app.open_connection(
            hostname, port=port, camera=camera, write_config=write_config
        )
        self.update_ui()
    
    def close_connection(self, hostname):
        """Close connection if it exists"""
        self.app.remove_connection(hostname)
        self.update_ui()
    
    def manage_connections(self):
        """Open connection manager dialog"""
        dialog = QTConnectionManager(self, self.app.get_connections())
        dialog.connection_requested.connect(self.open_connection)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.update_ui()
    
    def set_active_connection(self, option):
        """Set the active connection"""
        self.app.set_active_connection(option if option != "None" else None)
        # self.update_ui()
    
    def update_ui(self):
        """Update UI state based on current connections"""
        connections = self.app.get_connections()
        
        # Update connection combo
        self.connection_combo.clear()
        options = list(connections.keys()) or ["None"]
        self.connection_combo.addItems(options)
        
        # Set current selection
        current_connection = self.app.get_active_connection()
        current_host = "None" if current_connection is None else current_connection.host
        self.connection_combo.setCurrentText(current_host)
        
        if len(connections) == 0:
            self.set_manual_control_btn_state(False)
            self.automatic_button.setChecked(False)
            self.automatic_button.setEnabled(False)
            self.video_thread.stop()
            self.draw_no_signal_display()
            return
            
        connection = self.app.get_active_connection()
        if connection is None:
            return
            
        # Update automatic button state
        if self.app.get_director() is None or self.app.is_manual_only():
            self.automatic_button.setEnabled(False)
        else:
            self.automatic_button.setEnabled(True)
        
        # Update control mode
        if connection.is_manual:
            self.set_manual_control_btn_state(True)
            self.automatic_button.setChecked(False)
        else:
            self.set_manual_control_btn_state(False)
            self.automatic_button.setChecked(True)
        
        # Update continuous mode
        self.continuous_button.setChecked(
            self.app.get_control_mode() == ControlMode.CONTINUOUS
        )
        
        # Start video thread if not running
        if not self.video_thread.isRunning():
            self.video_thread.start()
    
    def toggle_command_mode(self, checked):
        """Toggle between manual and automatic mode"""
        self.app.toggle_director()
        self.update_ui()
    
    def toggle_continuous_mode(self, checked):
        """Toggle continuous/discrete mode"""
        # mode = ControlMode.CONTINUOUS if checked else ControlMode.DISCRETE
        # self.app.set_control_mode(mode)
        self.app.toggle_control_mode()
    
    def change_model(self, model_name):
        """Change the detection model"""
        self.app.change_model(model_name)
    
    def set_manual_control_btn_state(self, enabled):
        """Enable or disable manual control buttons"""
        self.up_button.setEnabled(enabled)
        self.down_button.setEnabled(enabled)
        self.left_button.setEnabled(enabled)
        self.right_button.setEnabled(enabled)
        self.home_button.setEnabled(enabled)
    
    def closeEvent(self, event):
        """Handle window close event"""
        if self._term is not None:
            remove_termination_handler(self._term)
            self._term = None
        
        # Stop video thread
        if self.video_thread.isRunning():
            self.video_thread.stop()
        
        # Cleanup scheduler
        if hasattr(self.scheduler, 'cleanup'):
            self.scheduler.cleanup()
        
        terminate(0, 0)
        event.accept()
