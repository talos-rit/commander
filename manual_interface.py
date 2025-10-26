import time
import tkinter
from enum import StrEnum
from threading import Thread

import customtkinter
from PIL import ImageTk

from config import CONFIG, add_config, load_config
from connection_manager import ConnectionManager
from publisher import Direction, Publisher
from tkscheduler import Scheduler
from tracking import MODEL_OPTIONS, USABLE_MODELS, Tracker
from utils import start_termination_guard, terminate

# Temporary hardcoded index to until config can be passed in on initialization
TEMP_CONFIG = CONFIG["unctalos.student.rit.edu"]


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


class ManualInterface(tkinter.Tk):
    """
    Representation of a manual interface used to control
    the robotic arm which holds the camera.
    """

    scheduler: Scheduler

    pressed_keys: set[Direction] = set()
    move_delay_ms = 300  # time inbetween each directional command being sent while directional button is depressed

    # Flags for director loop
    is_frame_loop_running = False
    director_thread = None
    director = None  # BaseDirector

    def __init__(self) -> None:
        """Constructor sets up tkinter manual interface, including buttons and labels"""
        super().__init__()
        start_termination_guard()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.scheduler = Scheduler(self)
        self.title("Talos Manual Interface")
        self.pressed_keys = set()  # keeps track of keys which are pressed down
        self.last_key_presses = {}
        self.tracker = Tracker(scheduler=self.scheduler)
        # publisher = Publisher(TEMP_CONFIG["socket_host"], TEMP_CONFIG["socket_port"])
        # publisher.start_socket_connection(self.scheduler)
        # self.after("idle", self.start_director_loop)

        self.config = load_config()
        self.connections = {}
        self.active_connection = None

        self.manual_mode = tkinter.BooleanVar(value=True)  # Control mode
        self.continuous_mode = tkinter.BooleanVar(value=True)  # continuous/discrete
        self.toggle_group = tkinter.Frame(self)
        self.toggle_group.grid(row=1, column=0)

        self.automatic_button = customtkinter.CTkSwitch(
            self.toggle_group,
            text=ButtonText.AUTOMATIC_MODE_LABEL,
            font=("Cascadia Code", 16, "bold"),
            command=self.toggle_command_mode,
        )
        self.automatic_button.pack(side="top", anchor="w", pady=5)

        self.cont_toggle_button = customtkinter.CTkSwitch(
            self.toggle_group,
            text=ButtonText.CONTINUOUS_MODE_LABEL,
            font=("Cascadia Code", 16, "bold"),
            variable=self.continuous_mode,
            onvalue=True,
            offvalue=False,
        )
        self.cont_toggle_button.pack(side="top", anchor="w")

        # setting up home button

        self.home_button = tkinter.Button(
            self,
            text=ButtonText.HOME,
            height=2,
            width=10,
            font=("Cascadia Code", 16, "bold"),
            command=self.move_home,
        )
        self.home_button.grid(row=2, column=1, padx=10, pady=10)

        # setting up directional buttons

        self.up_button = tkinter.Button(
            self,
            text=ButtonText.UP,
            height=2,
            width=10,
            font=("Cascadia Code", 16, "bold"),
        )
        self.up_button.grid(row=1, column=1, padx=10, pady=10)

        self.bind_button(self.up_button, Direction.UP)

        self.down_button = tkinter.Button(
            self,
            text=ButtonText.DOWN,
            height=2,
            width=10,
            font=("Cascadia Code", 16, "bold"),
        )
        self.down_button.grid(row=3, column=1, padx=10, pady=10)

        self.bind_button(self.down_button, Direction.DOWN)

        self.left_button = tkinter.Button(
            self,
            text=ButtonText.LEFT,
            height=2,
            width=10,
            font=("Cascadia Code", 16, "bold"),
        )
        self.left_button.grid(row=2, column=0, padx=10, pady=10)

        self.bind_button(self.left_button, Direction.LEFT)

        self.right_button = tkinter.Button(
            self,
            text=ButtonText.RIGHT,
            height=2,
            width=10,
            font=("Cascadia Code", 16, "bold"),
        )
        self.right_button.grid(row=2, column=2, padx=10, pady=10)

        self.bind_button(self.right_button, Direction.RIGHT)

        self.setup_keyboard_controls()

        # Setting up integrated video
        # Create a label that will display video frames.
        self.video_label = tkinter.Label(self)
        # This line ensures it stays on the top of the manual interface and centers it in the  middle
        self.video_label.grid(
            row=0, column=0, columnspan=6, padx=10, pady=10, sticky="nsew"
        )

        self.model_frame = tkinter.Frame(self)
        self.model_frame.grid(row=3, column=0)

        tkinter.Label(
            self.model_frame,
            text="Detection Model",
            font=("Cascadia Code", 16),
        ).pack(side="top", anchor="w")

        customtkinter.CTkOptionMenu(
            self.model_frame,
            variable=tkinter.StringVar(value="None"),
            values=MODEL_OPTIONS,
            command=self.set_mode,
            width=150,
            button_color="#4c4c4c",
            button_hover_color="#565656",
            fg_color="#2b2b2b",
        ).pack(side="top", anchor="w")

        self.loadAllButton = tkinter.Button(
            self,
            text="Connect all",
            font=("Cascadia Code", 10, "bold"),
            command=self.open_all_configured,
        )
        self.loadAllButton.grid(row=1, column=6, padx=10)

        self.manageConnectionsButton = tkinter.Button(
            self,
            text="Manage connections",
            font=("Cascadia Code", 10, "bold"),
            command=self.manage_connections,
        )
        self.manageConnectionsButton.grid(row=2, column=6, padx=10)

        self.selectedConnection = tkinter.StringVar(value="None")
        initial_options = self.connections if self.connections else ["None"]

        self.connectionMenu = tkinter.OptionMenu(
            self,
            self.selectedConnection,
            *initial_options,
            command=self.set_active_connection,
        )
        self.connectionMenu.config(width=10)
        self.connectionMenu.grid(row=3, column=6, padx=10)

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

    def bind_button(self, button, direction: Direction) -> None:
        """Shortens the constructor by binding button up/down presses.

        Args:
            button (tkinter.Button): button to bind with press and release functions
            direction (string): global variables for directional commands are provided at the top of this file
        """

        button.bind("<ButtonPress>", lambda event: self.start_move(direction))
        button.bind("<ButtonRelease>", lambda event: self.stop_move(direction))

    def open_connection(self, hostname: str) -> None:
        """Opens a new connection.

        Args:
            socket_host (string): the host ip address of the socket connection
            socket_port (int): the port number of the socket connection
        """
        if hostname in self.connections:
            print(f"Connection to {hostname} already exists")
            return
        port = self.config[hostname]["socket_port"]
        print(f"Opening connection to {hostname} on port {port}")
        publisher = Publisher(hostname, port)
        self.connections[hostname] = publisher
        self.update_connection_menu(new_selection=hostname)
        publisher.start_socket_connection(self.scheduler)
        self.after("idle", self.start_director_loop)

    def open_all_configured(self) -> None:
        """Loads all connections from the config file."""
        for hostname in self.config:
            self.open_connection(hostname)

    def open_new_connection(self, socket_host: str, socket_port: int) -> None:
        """Opens a new connection.

        Args:
            socket_host (string): the host ip address of the socket connection
            socket_port (int): the port number of the socket connection
        """
        print("This hasn't been implemented yet!!")
        # TODO do all the normal connection stuff
        # if successful:
        add_config(socket_host, socket_port)

    def close_connection(self, hostname: str) -> None:
        """Closes an existing connection.

        Args:
            socket_host (string): the host ip address of the socket connection
        """
        if hostname not in self.connections:
            print(f"Connection to {hostname} does not exist")
            return
        self.connections[hostname].close_connection()
        self.connections.pop(hostname)
        self.update_connection_menu()

    def start_move(self, direction: Direction) -> None:
        """Moves the robotic arm a static number of degrees per second.

        Args:
            direction (string): global variables for directional commands are provided at the top of this file
        """
        if not self.manual_mode.get():
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
        match direction:
            case Direction.UP:
                Publisher.polar_pan_discrete(0, 10, 1000, 3000)
                print("Polar pan discrete up")
            case Direction.DOWN:
                Publisher.polar_pan_discrete(0, -10, 1000, 3000)
                print("Polar pan discrete down")
            case Direction.LEFT:
                Publisher.polar_pan_discrete(-10, 0, 1000, 3000)
                print("Polar pan discrete left")
            case Direction.RIGHT:
                Publisher.polar_pan_discrete(10, 0, 1000, 3000)
                print("Polar pan discrete right")

    def stop_move(self, direction: Direction) -> None:
        """Stops a movement going the current direction.

        Args:
            direction (string): global variables for directional commands are provided at the top of this file
        """
        if not (self.manual_mode.get() and direction in self.pressed_keys):
            return
        if direction in self.last_key_presses:
            last_pressed_time = self.last_key_presses[direction]

            # Fix for operating systems that spam KEYDOWN KEYUP when a key is
            # held down:

            # I know this is jank but this is the best way I could figure out...
            # Time.sleep stops the whole function, so new key presses will not
            # be heard until after the sleep. So, create a new thread which is
            # async to wait for a new key press
            def stop_func() -> None:
                # Wait a fraction of a second
                time.sleep(0.05)
                # Get the last time the key was pressed again
                new_last_pressed_time = self.last_key_presses[direction]

                # Check if the key has been pressed or if the times are the same
                if new_last_pressed_time == last_pressed_time:
                    self.pressed_keys.remove(direction)
                    self.change_button_state(direction, "raised")

            # Start the thread
            thread = Thread(target=stop_func, daemon=True)
            thread.start()
            return
        self.pressed_keys.remove(direction)
        self.change_button_state(direction, "raised")

    def change_button_state(self, direction, depression) -> None:
        """Changes button state to sunken or raised based on input depression argument.

        Args:
            direction (enum): the directional button to change.
            depression (string): "raised" or "sunken", the depression state to change to.
        """

        match direction:
            case Direction.UP:
                self.up_button.config(relief=depression)
            case Direction.DOWN:
                self.down_button.config(relief=depression)
            case Direction.LEFT:
                self.left_button.config(relief=depression)
            case Direction.RIGHT:
                self.right_button.config(relief=depression)

        if self.continuous_mode.get() and len(self.pressed_keys) == 0:
            Publisher.polar_pan_continuous_stop()

    def keep_moving(self, direction: Direction) -> None:
        """Continuously allows moving to continue as controls are pressed and stops them once released by recursively calling this function while
            the associated directional is being pressed.

        Args:
            direction (_type_): global variables for directional commands are provided at the top of this file
        """
        if not self.continuous_mode.get():
            return

        self.after(self.move_delay_ms, lambda: self.keep_moving(direction))

        if len(self.pressed_keys) > 0:
            Publisher.polar_pan_continuous_direction_start(sum(self.pressed_keys))

    def move_home(self) -> None:
        """Moves the robotic arm from its current location to its home position"""
        Publisher.home(1000)

    def manage_connections(self) -> None:
        """Opens a pop-up window to manage socket connections."""
        ConnectionManager(self, self.connections, self.config)

    def set_active_connection(self, option: str | None = None) -> None:
        if option is None or option not in self.connections:
            print(f"Connection was not found or was None... (found {option})")
            return
        self.active_connection = option
        print(f"Active connection set to: {self.active_connection}")

    def update_connection_menu(self, new_selection=None):
        """Refresh dropdown menu to show the latest connections"""
        menu = self.connectionMenu["menu"]
        menu.delete(0, "end")  # clear old options

        if self.connections:
            for conn in self.connections:
                menu.add_command(
                    label=conn,
                    command=lambda value=conn: self.selectedConnection.set(value),
                )
            # If a new connection was added, switch to it
            if new_selection and new_selection in self.connections:
                self.selectedConnection.set(new_selection)
            # Otherwise, keep the current one if it still exists
            elif self.selectedConnection.get() not in self.connections:
                first_key = next(iter(self.connections))
                self.selectedConnection.set(first_key)
        else:
            menu.add_command(
                label="None", command=lambda: self.selectedConnection.set("None")
            )
            self.selectedConnection.set("None")

    def start_director_loop(self) -> None:
        self.is_frame_loop_running = True
        self.last_mode = None
        self.change_model()  # start model
        self.after(0, self.frame_loop)

    def frame_loop(self) -> None:
        """the director loop"""
        if not self.is_frame_loop_running:
            print("Ending director loop")
            return

        img = self.tracker.create_imagetk()
        if img is not None:
            self.update_video_frame(img)
        self.after(20, self.frame_loop)

    def set_mode(self, new_mode) -> None:
        if new_mode == "None":
            return self.change_model(None)
        self.change_model(new_mode)

    def update_video_frame(self, img: ImageTk.PhotoImage) -> None:
        self.video_label.config(image=img)
        # Keep a reference to prevent gc
        # see https://stackoverflow.com/questions/48364168/flickering-video-in-opencv-tkinter-integration
        self.video_label.dumb_image_ref = img  # pyright: ignore[reportAttributeAccessIssue]

    def change_model(self, option: str | None = None) -> None:
        if self.director is not None:
            self.tracker.stop_detection_process()
            self.director.stop_auto_control()
            self.director = None
        if option is None or option not in USABLE_MODELS:
            print(
                f"Model option was None or Not found skipping initialization... (found {option})"
            )
            return
        print(f"Entering {option}")
        model_class, director_class = USABLE_MODELS[option]
        self.director = director_class(self.tracker, self.scheduler)
        self.tracker.swap_model(model_class)

    # def toggle_continuous_mode(self) -> None:
    #     self.continuous_mode = not self.continuous_mode

    # if self.continuous_mode:
    #     self.cont_mode_label.config(text=ButtonText.CONTINUOUS_MODE_LABEL)
    # else:
    #     self.cont_mode_label.config(text=ButtonText.DISCRETE_MODE_LABEL)

    def toggle_command_mode(self) -> None:
        """Toggles command mode between manual mode and automatic mode.
        Disables all other controls when in automatic mode.
        """
        self.manual_mode.set(not self.manual_mode.get())

        if self.manual_mode.get():
            if self.director is not None:
                self.director.stop_auto_control()

            self.up_button.config(state="normal")
            self.down_button.config(state="normal")
            self.left_button.config(state="normal")
            self.right_button.config(state="normal")

            self.home_button.config(state="normal")

            self.is_frame_loop_running = False
            self.pressed_keys = set()
            return

        if self.director is not None:
            self.director.start_auto_control()
        else:
            print("director not found")

        self.up_button.config(state="disabled")
        self.down_button.config(state="disabled")
        self.left_button.config(state="disabled")
        self.right_button.config(state="disabled")

        self.home_button.config(state="disabled")

        self.pressed_keys = {
            Direction.UP,
            Direction.DOWN,
            Direction.LEFT,
            Direction.RIGHT,
        }

    def destroy(self):
        terminate(0, 0)
        super().destroy()
