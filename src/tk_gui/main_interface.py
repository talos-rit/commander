import tkinter as tk
from enum import StrEnum
from typing import Literal

import customtkinter as ctk
import cv2
import sv_ttk
from loguru import logger
from PIL import Image, ImageDraw, ImageTk

import assets
from src.connection.publisher import Direction
from src.talos_app import App, ControlMode
from src.tk_gui.connection_manager import TKConnectionManager
from src.tk_gui.styles import (BORDER_STYLE, BTN_STYLE,
                               CONTROL_BTN_GRID_FIT_STYLE, CONTROL_BTN_STYLE,
                               IS_SYSTEM_DARK, OPTIONS_MENU_STYLE,
                               THEME_FRAME_BG_COLOR)
from src.tk_gui.tkscheduler import TKIterativeTask, TKScheduler
from src.tracking import MODEL_OPTIONS
from src.utils import (add_termination_handler, remove_termination_handler,
                       start_termination_guard, terminate)

def set_mac_icon(icon_path: str) -> None:
    try:
        from Cocoa import NSApplication, NSImage  # type: ignore
    except ImportError:
        logger.warning("Unable to import pyobjc modules")
    else:
        ns_application = NSApplication.sharedApplication()
        logo_ns_image = NSImage.alloc().initByReferencingFile_(icon_path)
        ns_application.setApplicationIconImage_(logo_ns_image)


class ButtonText(StrEnum):
    """Button text Enum for interface controls"""

    # button text
    UP = "\u2191"
    DOWN = "\u2193"
    LEFT = "\u2190"
    RIGHT = "\u2192"
    HOME = "🏠 Home"

    # toggle switch labels
    CONTINUOUS_MODE_LABEL = "Continuous"
    AUTOMATIC_MODE_LABEL = "Automatic"


DIRECTIONAL_KEY_BINDING_MAPPING = {
    "Up": Direction.UP,
    "Down": Direction.DOWN,
    "Left": Direction.LEFT,
    "Right": Direction.RIGHT,
}


class TKInterface(tk.Tk):
    """
    Representation of a manual interface used to control
    the robotic arm which holds the camera.
    """

    app: App
    scheduler: TKScheduler
    display_loop_task: TKIterativeTask | None = None  # display loop task handle
    move_delay_ms = 300  # time inbetween each directional command being sent while directional button is depressed
    _term: int | None = None

    def __init__(self) -> None:
        """Constructor sets up tkinter manual interface, including buttons and labels"""
        super().__init__()
        sv_ttk.set_theme("dark" if IS_SYSTEM_DARK else "light")
        start_termination_guard()
        self._term = add_termination_handler(super().destroy)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.scheduler = TKScheduler(self)
        self.app = App()
        self.title("Talos Manual Interface")
        icon_path, icon_type = assets.get_icon()
        if icon_path is not None:
            if icon_type == "icns":
                set_mac_icon(icon_path)
            else:
                self.iconbitmap(icon_path)
        self.no_signal_display = self.draw_no_signal_display()

        container = tk.Frame(self)
        container.pack(fill="both", expand=True)
        container.rowconfigure(0, weight=3)
        container.rowconfigure([1, 2, 3], weight=1)
        container.columnconfigure([0, 1, 2], weight=1)

        self.toggle_group = ctk.CTkFrame(
            container,
            corner_radius=10,
            **BORDER_STYLE,
        )
        self.toggle_group.grid(row=1, column=0, padx=2, pady=2, sticky="nsew")
        self.toggle_group.columnconfigure([0, 2], weight=1)
        self.toggle_group.rowconfigure([0, 3], weight=1)

        self.automatic_button = ctk.CTkSwitch(
            self.toggle_group,
            text=ButtonText.AUTOMATIC_MODE_LABEL,
            font=("Cascadia Code", 16, "bold"),
            command=self.toggle_command_mode,
        )
        self.automatic_button.grid(row=1, column=1, sticky="ew")
        self.automatic_button.configure(state="disabled")

        self.continuous_mode = tk.StringVar(
            value=self.app.get_control_mode()
        )  # continuous/discrete
        self.cont_toggle_button = ctk.CTkSwitch(
            self.toggle_group,
            text=ButtonText.CONTINUOUS_MODE_LABEL,
            font=("Cascadia Code", 16, "bold"),
            variable=self.continuous_mode,
            command=self.app.toggle_control_mode,
            onvalue=ControlMode.CONTINUOUS,
            offvalue=ControlMode.DISCRETE,
        )
        self.cont_toggle_button.grid(row=2, column=1, sticky="ew")

        self.home_button = ctk.CTkButton(
            container,
            text=ButtonText.HOME,
            command=self.app.move_home,
            **BTN_STYLE,
            **CONTROL_BTN_STYLE,
        )
        self.home_button.grid(row=2, column=1, **CONTROL_BTN_GRID_FIT_STYLE)

        self.up_button = ctk.CTkButton(
            container,
            text=ButtonText.UP,
            **BTN_STYLE,
            **CONTROL_BTN_STYLE,
        )
        self.up_button.grid(row=1, column=1, **CONTROL_BTN_GRID_FIT_STYLE)
        self.bind_directional_button(self.up_button, Direction.UP)

        self.down_button = ctk.CTkButton(
            container,
            text=ButtonText.DOWN,
            **BTN_STYLE,
            **CONTROL_BTN_STYLE,
        )
        self.down_button.grid(row=3, column=1, **CONTROL_BTN_GRID_FIT_STYLE)
        self.bind_directional_button(self.down_button, Direction.DOWN)

        self.left_button = ctk.CTkButton(
            container,
            text=ButtonText.LEFT,
            **BTN_STYLE,
            **CONTROL_BTN_STYLE,
        )
        self.left_button.grid(row=2, column=0, **CONTROL_BTN_GRID_FIT_STYLE)
        self.bind_directional_button(self.left_button, Direction.LEFT)

        self.right_button = ctk.CTkButton(
            container,
            text=ButtonText.RIGHT,
            **BTN_STYLE,
            **CONTROL_BTN_STYLE,
        )
        self.right_button.grid(row=2, column=2, **CONTROL_BTN_GRID_FIT_STYLE)
        self.bind_directional_button(self.right_button, Direction.RIGHT)

        self.setup_keyboard_controls()
        self.set_manual_control_btn_state("disabled")

        # Setting up integrated video
        # Create a label that will display video frames.
        self.video_label = tk.Label(container)
        self.video_label.grid(
            row=0, column=0, columnspan=3, padx=10, pady=10, sticky="nsew"
        )
        self.update_display(self.no_signal_display)

        self.model_frame = ctk.CTkFrame(container, corner_radius=10, **BORDER_STYLE)
        self.model_frame.grid(row=3, column=0, padx=2, pady=2, sticky="nsew")
        self.model_frame.rowconfigure(1, weight=1)
        self.model_frame.columnconfigure(0, weight=1)

        tk.Label(
            self.model_frame,
            text="Detection Model",
            font=("Cascadia Code", 16),
            bg=THEME_FRAME_BG_COLOR,
        ).grid(row=0, column=0, pady=5, padx=5, sticky="ew")

        self.model_menu = ctk.CTkOptionMenu(
            self.model_frame,
            variable=tk.StringVar(value="None"),
            values=["None"] + MODEL_OPTIONS,
            command=self.change_model,
            **OPTIONS_MENU_STYLE,  # pyright: ignore[reportArgumentType]
        )
        self.model_menu.grid(row=2, column=0, pady=5, padx=5, sticky="ew")

        connection_frame = ctk.CTkFrame(
            container,
            corner_radius=10,
            **BORDER_STYLE,
        )
        connection_frame.grid(row=3, column=2, padx=2, pady=2, sticky="nsew")
        connection_frame.columnconfigure(0, weight=1)

        self.manageConnectionsButton = ctk.CTkButton(
            connection_frame,
            text="Manage connections",
            command=self.manage_connections,
            **{**BTN_STYLE, "bg_color": THEME_FRAME_BG_COLOR},
        )
        self.manageConnectionsButton.grid(
            row=0, column=0, ipady=2, padx=5, pady=5, sticky="ew"
        )

        self.selectedConnection = tk.StringVar(value="None")
        self.selectedConnection.trace_add(
            "write",
            lambda *_: self.set_active_connection(self.selectedConnection.get()),
        )
        self.connectionMenuList = list(self.app.get_connections().keys()) or ["None"]
        self.connectionMenu = ctk.CTkOptionMenu(
            connection_frame,
            variable=self.selectedConnection,
            values=self.connectionMenuList,
            command=self.set_active_connection,
            **OPTIONS_MENU_STYLE,  # pyright: ignore[reportArgumentType]
        )
        self.connectionMenu.grid(row=1, column=0, padx=5, pady=5, sticky="ew")

    def setup_keyboard_controls(self) -> None:
        """Does the tedious work of binding the keyboard arrow keys to the button controls."""
        for key, dir in DIRECTIONAL_KEY_BINDING_MAPPING.items():
            self.bind(f"<KeyPress-{key}>", lambda _, d=dir: self.app.start_move(d))
            self.bind(f"<KeyRelease-{key}>", lambda _, d=dir: self.app.stop_move(d))

    def bind_directional_button(
        self, button: ctk.CTkButton, direction: Direction
    ) -> None:
        """binds button press and release events to start and stop movement respectively"""
        button.bind("<Button-1>", lambda _, d=direction: self.app.start_move(d))
        button.bind("<ButtonRelease-1>", lambda _, d=direction: self.app.stop_move(d))

    def draw_no_signal_display(self) -> ImageTk.PhotoImage:
        no_signal_image = Image.new("RGB", (500, 380), color="gray")
        draw = ImageDraw.Draw(no_signal_image)
        draw.text((225, 180), "No Signal", fill="white")
        return ImageTk.PhotoImage(no_signal_image)

    def open_connection(
        self,
        hostname: str,
        port: int | None = None,
        camera: int | None = None,
        write_config=False,
    ) -> None:
        """Opens a new connection. Port and camera are supplied only if opening a new connection not from config.
        Args:
            hostname (string): the host ip address of the socket connection
            port (int): the port number of the socket connection(default picked from config)
            camera (int): the index of the camera to use for this connection(default picked from config)
        """
        self.app.open_connection(hostname)
        self.update_ui()

    def close_connection(self, hostname: str) -> None:
        """Closes hostname connection if it exists"""
        self.app.remove_connection(hostname)
        self.update_ui()

    def _set_modal_lock(self, locked: bool) -> None:
        self._modal_open = locked
        state = "disabled" if locked else "normal"
        self.manageConnectionsButton.configure(state=state)
        self.connectionMenu.configure(state=state)
        self.model_menu.configure(state=state)
        self.cont_toggle_button.configure(state=state)
        self.automatic_button.configure(state=state)
        self.set_manual_control_btn_state("disabled" if locked else "normal")

    def manage_connections(self) -> None:
        """Opens a pop-up window to manage socket connections."""
        self._set_modal_lock(True)
        dialog = TKConnectionManager(self, self.app, self.update_ui)
        self.wait_window(dialog)
        self._set_modal_lock(False)

    def set_active_connection(self, option) -> None:
        self.app.set_active_connection(option if option != "None" else None)
        self.update_ui()

    def update_ui(self) -> None:
        if len(self.app.get_connections()) == 0:
            self.set_manual_control_btn_state("disabled")
            self.automatic_button.deselect()
            self.automatic_button.configure(state="disabled")
            logger.debug("AUTOMATIC BUTTON DISABLED")
            self.cancel_display_loop()
            return self.update_connection_menu()
        if (connection := self.app.get_active_connection()) is None:
            return
        if self.app.get_director() is None or self.app.is_manual_only():
            self.automatic_button.configure(state="disabled")
            logger.debug("AUTOMATIC BUTTON DISABLED")
        else:
            self.automatic_button.configure(state="normal")
            logger.debug("AUTOMATIC BUTTON ENABLED")
        if connection.is_manual:
            self.set_manual_control_btn_state("normal")
            self.automatic_button.deselect()
        else:
            self.set_manual_control_btn_state("disabled")
            self.automatic_button.select()
        self.continuous_mode.set(self.app.get_control_mode())
        self.update_connection_menu()
        if not self.display_loop_task:
            self.after("idle", self.start_display_loop)

    def update_connection_menu(self):
        """Refresh dropdown menu to show the latest connections"""
        options = self.app.get_connections().keys()
        self.connectionMenu.configure(values=options)
        current_connection = self.app.get_active_connection()
        host = "None" if current_connection is None else current_connection.host
        self.selectedConnection.set(host)

    def start_display_loop(self) -> None:
        self.display_loop_task = self.scheduler.set_interval(50, self.display_loop)

    def cancel_display_loop(self) -> None:
        if self.display_loop_task is None:
            return
        self.display_loop_task.cancel()
        self.display_loop_task = None
        self.update_display(self.no_signal_display)

    def display_loop(self) -> None:
        """Video display loop"""
        frame = self.app.get_active_frame()
        img = self.convert_frame_to_tkimage(frame)
        self.update_display(img or self.no_signal_display)

    def convert_frame_to_tkimage(self, frame) -> ImageTk.PhotoImage | None:
        """Convert frame to tkinter image"""
        if frame is None or (config_data := self.app.get_active_config()) is None:
            return None
        desired_height = config_data.frame_height
        desired_width = config_data.frame_width
        frame_rgb = cv2.cvtColor(src=frame, code=cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)

        dim = (desired_width, desired_height)
        if desired_height is None:
            # Set desired dimensions (adjust these values as needed)
            aspect_ratio = float(frame.shape[1]) / float(frame.shape[0])
            new_height = int(desired_width / aspect_ratio)
            dim = (desired_width, new_height)
        assert dim[0] is not None and dim[1] is not None
        pil_image = pil_image.resize(dim, Image.Resampling.LANCZOS)  # pyright: ignore[reportArgumentType]
        return ImageTk.PhotoImage(image=pil_image)

    def update_display(self, img: ImageTk.PhotoImage) -> None:
        self.video_label.config(image=img)
        # Keep a reference to prevent gc
        # see https://stackoverflow.com/questions/48364168/flickering-video-in-opencv-tkinter-integration
        self.video_label.dumb_image_ref = img  # pyright: ignore[reportAttributeAccessIssue]

    def toggle_command_mode(self) -> None:
        """Toggles command mode between manual mode and automatic mode.
        Disables all other controls when in automatic mode.
        """
        self.app.toggle_director()
        self.update_ui()

    def change_model(self, model_name: str) -> None:
        """Changes the detection model used by the active connection."""
        self.app.change_model(model_name)
        self.update_ui()

    def set_manual_control_btn_state(
        self, state: Literal["normal", "active", "disabled"]
    ) -> None:
        """Enables or disables all manual control buttons.

        Args:
            state (string): "normal" or "disabled", the state to set all buttons to.
        """
        if state not in ("normal", "active", "disabled"):
            raise ValueError(f"Invalid state: {state!r}")

        self.up_button.configure(state=state)
        self.down_button.configure(state=state)
        self.left_button.configure(state=state)
        self.right_button.configure(state=state)
        self.home_button.configure(state=state)

    def destroy(self):
        if self._term is not None:
            # This only gets called by the tkinter, so we can safely remove the termination handler here
            # to prevent double calls
            remove_termination_handler(self._term)
            self._term = None
        terminate(0, 0)
        super().destroy()

    def get_app(self) -> App:
        return self.app
