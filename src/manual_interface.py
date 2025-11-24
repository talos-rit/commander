import time
import tkinter as tk
from enum import StrEnum
from typing import Literal

import customtkinter as ctk
import cv2
import sv_ttk
from PIL import Image, ImageDraw, ImageTk

from src.config import load_config, load_default_config
from src.connection_manager import ConnectionData, ConnectionManager
from src.publisher import Direction, Publisher
from src.styles import (
    BORDER_STYLE,
    BTN_STYLE,
    CONTROL_BTN_GRID_FIT_STYLE,
    CONTROL_BTN_STYLE,
    IS_SYSTEM_DARK,
    OPTIONS_MENU_STYLE,
    THEME_FRAME_BG_COLOR,
)
from src.tkscheduler import Scheduler
from src.tracking import MODEL_OPTIONS, USABLE_MODELS, Tracker
from src.utils import (
    add_termination_handler,
    remove_termination_handler,
    start_termination_guard,
    terminate,
)


class ButtonText(StrEnum):
    """Button text Enum for interface controls"""

    # button text
    UP = "\u2191"
    DOWN = "\u2193"
    LEFT = "\u2190"
    RIGHT = "\u2192"
    HOME = "🏠 Home"
    SWITCH = " ⤭ "

    # button labels
    CONTINUOUS_MODE_LABEL = "Continuous"
    DISCRETE_MODE_LABEL = "Discrete"
    MANUAL_MODE_LABEL = "Manual"
    AUTOMATIC_MODE_LABEL = "Automatic"


class ManualInterface(tk.Tk):
    """
    Representation of a manual interface used to control
    the robotic arm which holds the camera.
    """

    scheduler: Scheduler
    director = None
    run_display_loop = False  # Flag for display loop
    pressed_keys: set[Direction] = set()
    move_delay_ms = 300  # time inbetween each directional command being sent while directional button is depressed
    config: dict = load_config()
    default_config: dict = load_default_config()
    _term: int | None = None

    def __init__(self) -> None:
        """Constructor sets up tkinter manual interface, including buttons and labels"""
        super().__init__()
        # ctk.DrawEngine.preferred_drawing_method = "circle_shapes"
        sv_ttk.set_theme("dark" if IS_SYSTEM_DARK else "light")
        start_termination_guard()
        self._term = add_termination_handler(super().destroy)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.scheduler = Scheduler(self)
        self.title("Talos Manual Interface")
        self.pressed_keys = set()  # keeps track of keys which are pressed down
        self.last_key_presses = {}

        self.config = load_config()
        self.connections = dict()
        self.active_connection: None | str = None
        self.tracker = Tracker(self.connections, scheduler=self.scheduler)
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

        self.continuous_mode = tk.BooleanVar(value=True)  # continuous/discrete
        self.cont_toggle_button = ctk.CTkSwitch(
            self.toggle_group,
            text=ButtonText.CONTINUOUS_MODE_LABEL,
            font=("Cascadia Code", 16, "bold"),
            variable=self.continuous_mode,
            onvalue=True,
            offvalue=False,
        )
        self.cont_toggle_button.grid(row=2, column=1, sticky="ew")

        # setting up home button

        self.home_button = ctk.CTkButton(
            container,
            text=ButtonText.HOME,
            command=self.move_home,
            **BTN_STYLE,
            **CONTROL_BTN_STYLE,
        )
        self.home_button.grid(row=2, column=1, **CONTROL_BTN_GRID_FIT_STYLE)

        # setting up directional buttons

        self.up_button = ctk.CTkButton(
            container,
            text=ButtonText.UP,
            command=lambda: self.start_move(Direction.UP),
            **BTN_STYLE,
            **CONTROL_BTN_STYLE,
        )
        self.up_button.grid(row=1, column=1, **CONTROL_BTN_GRID_FIT_STYLE)
        self.bind_button(self.up_button, Direction.UP)

        self.down_button = ctk.CTkButton(
            container,
            text=ButtonText.DOWN,
            command=lambda: self.start_move(Direction.DOWN),
            **BTN_STYLE,
            **CONTROL_BTN_STYLE,
        )
        self.down_button.grid(row=3, column=1, **CONTROL_BTN_GRID_FIT_STYLE)
        self.bind_button(self.down_button, Direction.DOWN)

        self.left_button = ctk.CTkButton(
            container,
            text=ButtonText.LEFT,
            **BTN_STYLE,
            **CONTROL_BTN_STYLE,
        )
        self.left_button.grid(row=2, column=0, **CONTROL_BTN_GRID_FIT_STYLE)
        self.bind_button(self.left_button, Direction.LEFT)

        self.right_button = ctk.CTkButton(
            container,
            text=ButtonText.RIGHT,
            command=lambda: self.start_move(Direction.RIGHT),
            **BTN_STYLE,
            **CONTROL_BTN_STYLE,
        )
        self.right_button.grid(row=2, column=2, **CONTROL_BTN_GRID_FIT_STYLE)

        self.bind_button(self.right_button, Direction.RIGHT)

        self.setup_keyboard_controls()
        self.toggle_controls("disabled")

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

        options = ["None"] + MODEL_OPTIONS
        ctk.CTkOptionMenu(
            self.model_frame,
            variable=tk.StringVar(value="None"),
            values=options,
            command=self.set_mode,
            **OPTIONS_MENU_STYLE,  # pyright: ignore[reportArgumentType]
        ).grid(row=2, column=0, pady=5, padx=5, sticky="ew")

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
            lambda *args: self.set_active_connection(self.selectedConnection.get()),
        )
        self.connectionMenuList = (
            list(self.connections.keys()) if self.connections else ["None"]
        )

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
        self.bind("<KeyPress-Up>", lambda event: self.start_move(Direction.UP))
        self.bind("<KeyRelease-Up>", lambda event: self.stop_move(Direction.UP))

        self.bind("<KeyPress-Down>", lambda event: self.start_move(Direction.DOWN))
        self.bind("<KeyRelease-Down>", lambda event: self.stop_move(Direction.DOWN))

        self.bind("<KeyPress-Left>", lambda event: self.start_move(Direction.LEFT))
        self.bind("<KeyRelease-Left>", lambda event: self.stop_move(Direction.LEFT))

        self.bind("<KeyPress-Right>", lambda event: self.start_move(Direction.RIGHT))
        self.bind("<KeyRelease-Right>", lambda event: self.stop_move(Direction.RIGHT))

    def bind_button(self, button: ctk.CTkButton, direction: Direction) -> None:
        """Shortens the constructor by binding button up/down presses.

        Args:
            button (ctk.CTkButton): button to bind with press and release functions
            direction (string): global variables for directional commands are provided at the top of this file
        """

        button.bind("<Button-1>", lambda event: self.start_move(direction))
        button.bind("<ButtonRelease-1>", lambda event: self.stop_move(direction))

    def draw_no_signal_display(self) -> ImageTk.PhotoImage:
        no_signal_image = Image.new("RGB", (500, 380), color="gray")
        draw = ImageDraw.Draw(no_signal_image)
        draw.text((225, 180), "No Signal", fill="white")
        image_tk = ImageTk.PhotoImage(no_signal_image)
        return image_tk

    def open_connection(
        self, hostname: str, port=None, camera=None, write_config=False
    ) -> None:
        """Opens a new connection. Port and camera are supplied only if opening a new connection not from config.
        Args:
            socket_host (string): the host ip address of the socket connection
            socket_port (int): the port number of the socket connection
            camera (int): the index of the camera to use for this connection
        """
        if hostname in self.connections:
            print(f"Connection to {hostname} already exists")
            return
        # If port is not supplied, get it from config
        if port is None:
            port = self.config[hostname]["socket_port"]
        # If camera is not supplied, get it from config
        if camera is None:
            camera = self.config[hostname]["camera_index"]
        publisher = Publisher(hostname, port)
        conn = ConnectionData(hostname, port, camera, publisher)
        self.connections[hostname] = conn
        self.set_active_connection(hostname)
        frame_shape = self.tracker.add_capture(hostname, camera, conn.fps)
        conn.set_frame_shape(frame_shape)
        publisher.start_socket_connection(self.scheduler)
        if write_config:
            self.config = load_config()
        if self.director is not None:
            if frame_shape is not None:
                self.director.add_control_feed(
                    hostname, conn.manual, frame_shape, publisher=publisher
                )

    def open_all_configured(self) -> None:
        """Loads all connections from the config file."""
        for i, hostname in enumerate(self.config):
            self.scheduler.set_timeout(
                i * 5000, lambda hostname=hostname: self.open_connection(hostname)
            )

    def close_connection(self, hostname: str) -> None:
        """Closes an existing connection.

        Args:
            socket_host (string): the host ip address of the socket connection
        """
        if hostname not in self.connections:
            print(f"Connection to {hostname} does not exist")
            return
        self.tracker.remove_capture(hostname)
        self.connections[hostname].publisher.close_connection()
        self.connections.pop(hostname)
        if self.active_connection == hostname:
            self.remove_active_connection()
        else:
            self.update_connection_menu()
        if self.director is not None:
            self.director.remove_control_feed(hostname)

    def start_move(self, direction: Direction) -> None:
        """Moves the robotic arm a static number of degrees per second.

        Args:
            direction (string): global variables for directional commands are provided at the top of this file
        """
        if not self.get_active_connection().manual or self.active_connection is None:
            return
        self.last_key_presses[direction] = time.time()

        if direction in self.pressed_keys:
            return
        self.pressed_keys.add(direction)

        self.change_button_state(direction, "sunken")

        if self.continuous_mode.get():
            self.keep_moving(direction)
            return
        # moves toward input direction by delta 10 (degrees)
        connectionData = self.connections.get(self.active_connection)
        if connectionData is None:
            print(
                f"[ERROR] No connection found for active connection: {self.active_connection}"
            )
            return
        publisher = connectionData.publisher
        match direction:
            case Direction.UP:
                publisher.polar_pan_discrete(0, 10, 1000, 3000)
                print("Polar pan discrete up")
            case Direction.DOWN:
                publisher.polar_pan_discrete(0, -10, 1000, 3000)
                print("Polar pan discrete down")
            case Direction.LEFT:
                publisher.polar_pan_discrete(10, 0, 1000, 3000)
                print("Polar pan discrete left")
            case Direction.RIGHT:
                publisher.polar_pan_discrete(-10, 0, 1000, 3000)
                print("Polar pan discrete right")

    def stop_move(self, direction: Direction) -> None:
        """Stops a movement going the current direction.

        Debounces key-up using tkinter's after instead of creating threads.
        """
        # Safely get the active connection; if none, do nothing.
        connectionData = None
        if self.active_connection is not None:
            connectionData = self.connections.get(self.active_connection)
        if (
            connectionData is None
            or not connectionData.manual
            or direction not in self.pressed_keys
        ):
            return

        # ensure the per-direction jobs dict exists
        if not hasattr(self, "_stop_move_jobs"):
            self._stop_move_jobs = {}

        # If we have a recorded last press time, schedule a short delayed check
        # instead of sleeping in a background thread. This lets new key presses
        # update last_key_presses and cancel/replace the pending job.
        if direction in self.last_key_presses:
            last_pressed_time = self.last_key_presses[direction]

            # cancel any previously scheduled job for this direction
            prev_job = self._stop_move_jobs.get(direction)
            if prev_job is not None:
                try:
                    self.after_cancel(prev_job)
                except Exception:
                    pass

            def finalize_stop() -> None:
                # If the press time hasn't changed, treat as a real release
                if self.last_key_presses.get(direction) == last_pressed_time:
                    if direction in self.pressed_keys:
                        self.pressed_keys.remove(direction)
                        self.change_button_state(direction, "raised")
                # clean up job entry
                self._stop_move_jobs.pop(direction, None)

            # schedule the delayed check (50 ms)
            job_id = self.after(50, finalize_stop)
            self._stop_move_jobs[direction] = job_id
            return

        # Fallback: immediate removal if no timestamp exists
        if direction in self.pressed_keys:
            self.pressed_keys.remove(direction)
        self.change_button_state(direction, "raised")

    def change_button_state(self, direction, depression) -> None:
        """Changes button state to sunken or raised based on input depression argument.

        Args:
            direction (enum): the directional button to change.
            depression (string): "raised" or "sunken", the depression state to change to.
        """

        # match direction:
        #     case Direction.UP:
        #         self.up_button.configure(relief=depression)
        #     case Direction.DOWN:
        #         self.down_button.configure(relief=depression)
        #     case Direction.LEFT:
        #         self.left_button.configure(relief=depression)
        #     case Direction.RIGHT:
        #         self.right_button.configure(relief=depression)

        if self.continuous_mode.get() and len(self.pressed_keys) == 0:
            connectionData = self.connections.get(self.active_connection)
            if connectionData is None:
                print(
                    f"[ERROR] No connection found for active connection: {self.active_connection}"
                )
                return
            publisher = connectionData.publisher
            publisher.polar_pan_continuous_stop()

    def keep_moving(self, direction: Direction) -> None:
        """Continuously allows moving to continue as controls are pressed and stops them once released by recursively calling this function while
            the associated directional is being pressed.

        Args:
            direction (_type_): global variables for directional commands are provided at the top of this file
        """
        if not self.continuous_mode.get():
            return
        if len(self.pressed_keys) == 0 or direction not in self.pressed_keys:
            return
        self.after(self.move_delay_ms, lambda: self.keep_moving(direction))
        connectionData = self.connections.get(self.active_connection)
        if connectionData is None:
            print(
                f"[ERROR] No connection found for active connection: {self.active_connection}"
            )
            return
        publisher = connectionData.publisher
        publisher.polar_pan_continuous_direction_start(sum(self.pressed_keys))

    def move_home(self) -> None:
        """Moves the robotic arm from its current location to its home position"""
        connectionData = self.get_active_connection()
        if connectionData is None:
            print(
                f"[ERROR] No connection found for active connection: {self.active_connection}"
            )
            return
        publisher = connectionData.publisher
        publisher.home(1000)

    def manage_connections(self) -> None:
        """Opens a pop-up window to manage socket connections."""
        ConnectionManager(self, self.connections)

    def set_active_connection(self, option) -> None:
        if option == self.active_connection or option == "None":
            return
        self.active_connection = option
        self.tracker.set_active_connection(option)
        self.update_ui()

    def remove_active_connection(self) -> None:
        if self.connections:
            self.set_active_connection(
                self.connections[next(iter(self.connections))].host
            )
        else:
            self.active_connection = None
            self.tracker.remove_active_connection()
            self.update_ui()

    def update_ui(self) -> None:
        if not self.connections:
            self.toggle_controls("disabled")
            self.automatic_button.deselect()
            self.automatic_button.configure(state="disabled")
            self.run_display_loop = False
            self.update_connection_menu()
        else:
            if self.director is None or self.get_active_connection().manual_only:
                self.automatic_button.configure(state="disabled")
            else:
                self.automatic_button.configure(state="normal")
            if self.get_active_connection().manual:
                self.toggle_controls("normal")
                self.automatic_button.deselect()
            else:
                self.toggle_controls("disabled")
                self.automatic_button.select()
            self.update_connection_menu(self.active_connection)
            if not self.run_display_loop:
                self.after("idle", self.start_display_loop)

    def get_active_connection(self) -> ConnectionData:
        return self.connections[self.active_connection]

    def update_connection_menu(self, new_selection=None):
        """Refresh dropdown menu to show the latest connections"""

        if not self.connections:
            self.selectedConnection.set("None")
            self.connectionMenu.configure(values=["None"])
            return

        options = list(self.connections.keys())
        self.connectionMenu.configure(values=options)

        # If a new connection was added, switch to it
        if new_selection and new_selection in self.connections:
            self.selectedConnection.set(new_selection)
        # Otherwise, keep the current one if it still exists
        elif self.selectedConnection.get() not in self.connections:
            first_key = next(iter(self.connections))
            self.selectedConnection.set(first_key)

    def start_display_loop(self) -> None:
        self.run_display_loop = True
        self.after(0, self.display_loop)

    def display_loop(self) -> None:
        """Video display loop"""
        if not self.run_display_loop:
            self.update_display(self.no_signal_display)
            return

        frame = self.tracker.get_frame()
        img = self.conv_cv2_frame_to_tkimage(frame)
        if img is not None:
            self.update_display(img)
        else:
            self.update_display(self.no_signal_display)
        self.after(20, self.display_loop)

    def conv_cv2_frame_to_tkimage(self, frame) -> ImageTk.PhotoImage | None:
        """Convert frame to tkinter image"""
        # Load config values
        if frame is None:
            return None
        if self.active_connection in self.config:
            config_data = self.config[self.active_connection]
        else:
            config_data = self.default_config
        desired_height: int | None = config_data.get("frame_height", None)
        desired_width: int | None = config_data.get("frame_width", None)
        frame_rgb = cv2.cvtColor(src=frame, code=cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)

        dim = (desired_width, desired_height)
        if desired_height is None:
            # Set desired dimensions (adjust these values as needed)
            new_width = desired_width or 500
            aspect_ratio = float(frame.shape[1]) / float(frame.shape[0])
            new_height = int(new_width / aspect_ratio)

            # Create the new dimensions tuple (width, height)
            dim = (new_width, new_height)
        assert dim[0] is not None and dim[1] is not None
        pil_image = pil_image.resize(dim, Image.Resampling.LANCZOS)  # pyright: ignore[reportArgumentType]
        return ImageTk.PhotoImage(image=pil_image)

    def set_mode(self, new_mode) -> None:
        if new_mode == "None":
            self.change_model(None)
        else:
            self.change_model(new_mode)

    def update_display(self, img: ImageTk.PhotoImage) -> None:
        self.video_label.config(image=img)
        # Keep a reference to prevent gc
        # see https://stackoverflow.com/questions/48364168/flickering-video-in-opencv-tkinter-integration
        self.video_label.dumb_image_ref = img  # pyright: ignore[reportAttributeAccessIssue]

    def change_model(self, option: str | None = None) -> None:
        if self.director is not None:
            print("Stopping previous model")
            self.director.stop_auto_control()
            self.director = None
        if option is None:
            print("Disabling model")
            self.automatic_button.configure(state="disabled")
            self.tracker.swap_model(None)
            return
        if option not in USABLE_MODELS:
            print(
                f"Model option was not found skipping initialization... (found {option})"
            )
            return
        print(f"Entering {option}")
        model_class, director_class = USABLE_MODELS[option]
        self.director = director_class(self.tracker, self.connections, self.scheduler)
        self.tracker.swap_model(model_class)
        if self.connections and not self.get_active_connection().manual_only:
            self.automatic_button.configure(state="normal")

    def toggle_command_mode(self) -> None:
        """Toggles command mode between manual mode and automatic mode.
        Disables all other controls when in automatic mode.
        """
        connection = self.get_active_connection()
        if self.get_active_connection().manual_only:
            print("Connection is set to manual only mode, cannot switch to automatic.")
            self.automatic_button.deselect()
            connection.set_manual(False)
            return
        connection.set_manual(not connection.manual)

        if connection.manual:
            if self.director is not None:
                self.director.update_control_feed(connection.host, True)

            self.toggle_controls("normal")

            self.pressed_keys = set()
            return

        if self.director is not None:
            self.director.update_control_feed(connection.host, False)
        else:
            print("director not found")

        self.toggle_controls("disabled")

        self.pressed_keys = {
            Direction.UP,
            Direction.DOWN,
            Direction.LEFT,
            Direction.RIGHT,
        }

    def toggle_controls(self, state: Literal["normal", "active", "disabled"]) -> None:
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
