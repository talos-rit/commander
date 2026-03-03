from enum import StrEnum

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QFrame,
    QComboBox,
    QSizePolicy,
    QDialog,
)
from PySide6.QtCore import Qt, Signal, QThread, QSignalBlocker
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QFont, QKeyEvent
import cv2
from loguru import logger
import numpy as np

from src.pyside_gui.qtwidgets import Toggle
from src.connection.publisher import Direction
from src.talos_app import App, ControlMode
from src.pyside_gui.connection_manager import QTConnectionManager
from src.pyside_gui.styles import get_main_stylesheet
from src.pyside_gui.qtscheduler import QTScheduler
from src.tracking import MODEL_OPTIONS
from src.utils import (
    add_termination_handler,
    remove_termination_handler,
    start_termination_guard,
    terminate,
)


class VideoThread(QThread):
    """Thread for processing video frames"""

    frame_processed = Signal(np.ndarray)

    def __init__(self, app: App):
        super().__init__()
        self.app = app
        self.running = True
        add_termination_handler(self.stop)

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
    HOME = "Home"
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
        main_layout.setColumnStretch(0, 1)
        main_layout.setColumnStretch(1, 1)
        main_layout.setColumnStretch(2, 1)

        self._setup_video_display(main_layout)
        main_layout.addWidget(self._build_toggle_frame(), 1, 0)
        self._setup_directional_controls(main_layout)
        main_layout.addWidget(self._build_model_frame(), 3, 0)
        main_layout.addWidget(self._build_connection_frame(), 3, 2)
        self.update_ui()

    def _setup_video_display(self, layout: QGridLayout) -> None:
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setMinimumSize(500, 380)
        self.video_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.video_label.setStyleSheet("border: 2px solid gray; background-color: black;")
        layout.addWidget(self.video_label, 0, 0, 1, 3)
        self.draw_no_signal_display()

    def _build_toggle_frame(self) -> QFrame:
        toggle_frame = QFrame()
        toggle_frame.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )
        toggle_frame.setMaximumWidth(240)
        toggle_layout = QVBoxLayout(toggle_frame)

        self.automatic_slider = Toggle()
        self.automatic_slider.setFont(QFont("Cascadia Code", 12, QFont.Weight.Bold))
        self.automatic_slider.toggled.connect(lambda checked: self.app.set_manual_control(not checked))
        self.automatic_slider.setEnabled(False)

        automatic_row_layout = QHBoxLayout()
        automatic_row_layout.setContentsMargins(0, 0, 0, 0)
        automatic_row_layout.setSpacing(10)
        automatic_label = QLabel(ButtonText.AUTOMATIC_MODE_LABEL)
        automatic_label.setFont(QFont("Cascadia Code", 12, QFont.Weight.Bold))
        automatic_row_layout.addWidget(self.automatic_slider)
        automatic_row_layout.addWidget(automatic_label)
        automatic_row_layout.addStretch(1)
        toggle_layout.addLayout(automatic_row_layout)

        self.continuous_slider = Toggle()
        self.continuous_slider.setFont(QFont("Cascadia Code", 12, QFont.Weight.Bold))
        self.continuous_slider.toggled.connect(lambda checked: self.app.set_control_mode(ControlMode.CONTINUOUS if checked else ControlMode.DISCRETE))

        continuous_row_layout = QHBoxLayout()
        continuous_row_layout.setContentsMargins(0, 0, 0, 0)
        continuous_row_layout.setSpacing(10)
        continuous_label = QLabel(ButtonText.CONTINUOUS_MODE_LABEL)
        continuous_label.setFont(QFont("Cascadia Code", 12, QFont.Weight.Bold))
        continuous_row_layout.addWidget(self.continuous_slider)
        continuous_row_layout.addWidget(continuous_label)
        continuous_row_layout.addStretch(1)
        toggle_layout.addLayout(continuous_row_layout)

        return toggle_frame

    def _setup_directional_controls(self, layout: QGridLayout) -> None:
        self.home_button = self._create_direction_button(
            ButtonText.HOME,
            on_click=self.app.move_home,
        )
        layout.addWidget(self.home_button, 2, 1)

        self.up_button = self._create_direction_button(
            ButtonText.UP,
            on_press=lambda: self.app.start_move(Direction.UP),
            on_release=lambda: self.app.stop_move(Direction.UP),
        )
        layout.addWidget(self.up_button, 1, 1)

        self.down_button = self._create_direction_button(
            ButtonText.DOWN,
            on_press=lambda: self.app.start_move(Direction.DOWN),
            on_release=lambda: self.app.stop_move(Direction.DOWN),
        )
        layout.addWidget(self.down_button, 3, 1)

        self.left_button = self._create_direction_button(
            ButtonText.LEFT,
            on_press=lambda: self.app.start_move(Direction.LEFT),
            on_release=lambda: self.app.stop_move(Direction.LEFT),
        )
        layout.addWidget(self.left_button, 2, 0)

        self.right_button = self._create_direction_button(
            ButtonText.RIGHT,
            on_press=lambda: self.app.start_move(Direction.RIGHT),
            on_release=lambda: self.app.stop_move(Direction.RIGHT),
        )
        layout.addWidget(self.right_button, 2, 2)

    def _create_direction_button(
        self,
        text: str,
        on_click=None,
        on_press=None,
        on_release=None,
    ) -> QPushButton:
        button = QPushButton(text)
        button.setFont(QFont("Cascadia Code", 16, QFont.Weight.Bold))
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        button.setMinimumSize(80, 80)

        if on_click is not None:
            button.clicked.connect(on_click)
        if on_press is not None:
            button.pressed.connect(on_press)
        if on_release is not None:
            button.released.connect(on_release)

        return button

    def _build_model_frame(self) -> QFrame:
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
        return model_frame

    def _build_connection_frame(self) -> QFrame:
        connection_frame = QFrame()
        connection_layout = QVBoxLayout(connection_frame)

        self.manage_connections_btn = QPushButton("Manage connections")
        self.manage_connections_btn.clicked.connect(self.manage_connections)
        connection_layout.addWidget(self.manage_connections_btn)

        self.connection_combo = QComboBox()
        self.connection_combo.currentTextChanged.connect(self.set_active_connection)
        connection_layout.addWidget(self.connection_combo)

        return connection_frame

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
        if frame is None or (config_data := self.app.get_active_config()) is None:
            return None

        desired_height = config_data.frame_height
        desired_width = config_data.frame_width

        # Convert BGR to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_frame.shape
        bytes_per_line = ch * w

        # Create QImage from numpy array
        qimage = QImage(
            rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888
        )

        # Resize if needed
        if desired_width and desired_height:
            qimage = qimage.scaled(
                desired_width,
                desired_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        elif desired_width:
            qimage = qimage.scaledToWidth(
                desired_width, Qt.TransformationMode.SmoothTransformation
            )

        # Convert to QPixmap and display
        pixmap = QPixmap.fromImage(qimage)
        self.video_label.setPixmap(pixmap)

    def manage_connections(self):
        """Open connection manager dialog"""
        dialog = QTConnectionManager(self, self.app)
        dialog.update_connections.connect(self.update_ui)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.update_ui()

    def set_active_connection(self, option):
        """Set the active connection"""
        if option:
            self.app.set_active_connection(option if option != "None" else None)
            self.update_ui()

    def update_connection_list(self):
        """Update the connection combo box list"""
        connections = self.app.get_connection_hosts()

        with QSignalBlocker(self.connection_combo):
            self.connection_combo.clear()
            options = list(connections) or ["None"]
            self.connection_combo.addItems(options)

            current_host = self.app.get_active_hostname() or "None"
            if self.connection_combo.currentText() != current_host:
                self.connection_combo.setCurrentText(current_host)

    def update_ui(self):
        """Update UI state based on current connections"""
        self.update_connection_list()

        if len(self.app.get_connection_hosts()) == 0:
            self.set_manual_control_btn_state(False)
            self.automatic_slider.setChecked(False)
            self.automatic_slider.setEnabled(False)
            self.video_thread.stop()
            self.draw_no_signal_display()
            return

        if (connection := self.app.get_active_connection()) is None:
            return

        # Update automatic button state
        if self.app.get_director() is None or self.app.is_manual_only():
            self.automatic_slider.setEnabled(False)
        else:
            self.automatic_slider.setEnabled(True)

        # Update control mode
        if connection.is_manual:
            self.set_manual_control_btn_state(True)
            self.automatic_slider.setChecked(False)
        else:
            self.set_manual_control_btn_state(False)
            self.automatic_slider.setChecked(True)

        # Update continuous mode
        self.continuous_slider.setChecked(
            self.app.get_control_mode() == ControlMode.CONTINUOUS
        )
        
        logger.info("UI updated. Active connection: {}, Manual control: {}, Control mode: {}", self.app.get_active_hostname(), self.app.get_manual_control(), self.app.get_control_mode())

        # Start video thread if not running
        if not self.video_thread.isRunning():
            self.video_thread.running = True
            self.video_thread.start()

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

        # Cleanup scheduler
        if hasattr(self.scheduler, "cleanup"):
            self.scheduler.cleanup()

        terminate(0, 0)
        event.accept()
