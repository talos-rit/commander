import time
import tkinter
from enum import IntEnum, StrEnum
from threading import Thread

from PIL import ImageTk

from directors import BaseDirector, ContinuousDirector
from publisher import Publisher
from tkscheduler import Scheduler
from tracking.keep_away.keep_away_director import KeepAwayDirector
from tracking.keep_away.keep_away_tracker import KeepAwayModel
from tracking.media_pipe.media_pipe_pose import MediaPipePoseModel
from tracking.media_pipe.media_pipe_tracker import MediaPipeModel
from tracking.tracker import Tracker
from tracking.yolo.yolo_tracker import YOLOModel


class Direction(IntEnum):
    """Directional Enum for interface controls"""

    UP = 1
    DOWN = 2
    LEFT = 3
    RIGHT = 4


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
    CONTINUOUS_MODE_LABEL = "Movement Mode: Continuous"
    DISCRETE_MODE_LABEL = "Movement Mode: Discrete"
    MANUAL_MODE_LABEL = "Control Mode: Manual"
    AUTOMATIC_MODE_LABEL = "Control Mode: Automatic"


class ManualInterface(tkinter.Tk):
    """
    Representation of a manual interface used to control
    the robotic arm which holds the camera.
    """

    scheduler: Scheduler

    pressed_keys: set = set()
    move_delay_ms = 300  # time inbetween each directional command being sent while directional button is depressed
    manual_mode = True  # True for manual, False for computer vision
    continuous_mode = True
    current_mode = "standard"

    # Flags for director loop
    is_frame_loop_running = False
    director_thread = None
    director: BaseDirector | None = None

    def __init__(self):
        """Constructor sets up tkinter manual interface, including buttons and labels"""
        super().__init__()
        self.scheduler = Scheduler(self)
        self.title("Talos Manual Interface")
        self.pressed_keys = set()  # keeps track of keys which are pressed down
        self.last_key_presses = {}
        self.tracker = Tracker(scheduler=self.scheduler)
        Publisher.start_socket_connection(self.scheduler)
        self.after("idle", self.start_director_loop)

        # setting up manual vs automatic control toggle
        self.mode_label = tkinter.Label(
            self,
            text=ButtonText.MANUAL_MODE_LABEL,
            font=("Cascadia Code", 12),
        )
        self.mode_label.grid(row=2, column=4)

        self.toggle_button = tkinter.Button(
            self,
            text=ButtonText.SWITCH,
            font=("Cascadia Code", 16, "bold"),
            command=self.toggle_command_mode,
        )
        self.toggle_button.grid(row=2, column=5, padx=10)

        # Setup up continuous/discrete toggle

        self.cont_mode_label = tkinter.Label(
            self,
            text=ButtonText.CONTINUOUS_MODE_LABEL,
            font=("Cascadia Code", 12),
        )
        self.cont_mode_label.grid(row=1, column=4)

        self.cont_toggle_button = tkinter.Button(
            self,
            text=ButtonText.SWITCH,
            font=("Cascadia Code", 16, "bold"),
            command=self.toggle_continuous_mode,
        )
        self.cont_toggle_button.grid(row=1, column=5, padx=10)

        # setting up home button

        self.home_button = tkinter.Button(
            self,
            text=ButtonText.HOME,
            font=("Cascadia Code", 16),
            command=self.move_home,
        )
        self.home_button.grid(row=3, column=4)

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

        # Set up keep away button
        # Keep‐Away mode toggle button
        self.keepaway_button = tkinter.Button(
            self,
            text="Play Keep Away",
            font=("Cascadia Code", 12),
            command=self.toggle_keep_away_mode,
        )
        self.keepaway_button.grid(row=2, column=6, padx=10)

        self.yolo_button = tkinter.Button(
            self,
            text="Yolo Tracker",
            font=("Cascadia Code", 12),
            command=self.toggle_yolo_mode,
        )
        self.yolo_button.grid(row=3, column=6, padx=10)

        self.media_pipe_pose_button = tkinter.Button(
            self,
            text="Media Pipe Pose Tracker",
            font=("Cascadia Code", 12),
            command=self.toggle_media_pipe_pose_mode,
        )
        self.media_pipe_pose_button.grid(row=4, column=6, padx=10)

    def setup_keyboard_controls(self):
        """Does the tedious work of binding the keyboard arrow keys to the button controls."""
        self.bind("<KeyPress-Up>", lambda event: self.start_move(Direction.UP))
        self.bind("<KeyRelease-Up>", lambda event: self.stop_move(Direction.UP))

        self.bind("<KeyPress-Down>", lambda event: self.start_move(Direction.DOWN))
        self.bind("<KeyRelease-Down>", lambda event: self.stop_move(Direction.DOWN))

        self.bind("<KeyPress-Left>", lambda event: self.start_move(Direction.LEFT))
        self.bind("<KeyRelease-Left>", lambda event: self.stop_move(Direction.LEFT))

        self.bind("<KeyPress-Right>", lambda event: self.start_move(Direction.RIGHT))
        self.bind("<KeyRelease-Right>", lambda event: self.stop_move(Direction.RIGHT))

    def bind_button(self, button, direction: Direction):
        """Shortens the constructor by binding button up/down presses.

        Args:
            button (tkinter.Button): button to bind with press and release functions
            direction (string): global variables for directional commands are provided at the top of this file
        """

        button.bind("<ButtonPress>", lambda event: self.start_move(direction))
        button.bind("<ButtonRelease>", lambda event: self.stop_move(direction))

    def start_move(self, direction: Direction):
        """Moves the robotic arm a static number of degrees per second.

        Args:
            direction (string): global variables for directional commands are provided at the top of this file
        """
        if not self.manual_mode:
            return
        self.last_key_presses[direction] = time.time()

        if direction in self.pressed_keys:
            return
        self.pressed_keys.add(direction)

        self.change_button_state(direction, "sunken")

        if self.continuous_mode:
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

    def stop_move(self, direction: Direction):
        """Stops a movement going the current direction.

        Args:
            direction (string): global variables for directional commands are provided at the top of this file
        """
        if not (self.manual_mode and direction in self.pressed_keys):
            return
        if direction in self.last_key_presses:
            last_pressed_time = self.last_key_presses[direction]

            # Fix for operating systems that spam KEYDOWN KEYUP when a key is
            # held down:

            # I know this is jank but this is the best way I could figure out...
            # Time.sleep stops the whole function, so new key presses will not
            # be heard until after the sleep. So, create a new thread which is
            # async to wait for a new key press
            def stop_func():
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

    def change_button_state(self, direction, depression):
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

        if self.continuous_mode and len(self.pressed_keys) == 0:
            Publisher.polar_pan_continuous_stop()
            print("Polar pan cont STOP")

    def keep_moving(self, direction: Direction):
        """Continuously allows moving to continue as controls are pressed and stops them once released by recursively calling this function while
            the associated directional is being pressed.

        Args:
            direction (_type_): global variables for directional commands are provided at the top of this file
        """
        if self.continuous_mode and len(self.pressed_keys) > 0:
            moving_azimuth = 0
            moving_altitude = 0

            # Use addition so that if two opposing keys are pressed it cancels out
            if Direction.UP in self.pressed_keys:
                moving_altitude += 1
            if Direction.DOWN in self.pressed_keys:
                moving_altitude -= 1
            if Direction.LEFT in self.pressed_keys:
                moving_azimuth += 1
            if Direction.RIGHT in self.pressed_keys:
                moving_azimuth -= 1

            print(
                f"Polar pan cont Azimuth: {moving_azimuth} Altitude: {moving_altitude}"
            )

            Publisher.polar_pan_continuous_start(
                moving_azimuth_int=moving_azimuth, moving_altitude_int=moving_altitude
            )

        if self.continuous_mode:
            self.after(
                self.move_delay_ms, lambda: self.keep_moving(direction)
            )  # lambda used as function reference to execute when required

    def move_home(self):
        """Moves the robotic arm from its current location to its home position"""
        print("Moving home")
        Publisher.home(1000)  # sends a command to move to home via the publisher

    def start_director_loop(self):
        self.is_frame_loop_running = True
        self.last_mode = None
        self.after(0, self.frame_loop)

    def frame_loop(self):
        """the director loop"""
        if not self.is_frame_loop_running:
            print("Ending director loop")
            return
        # if mode changed, tear down & rebuild
        if self.current_mode != self.last_mode:
            self.last_mode = self.current_mode
            if self.director is not None:
                self.director.stop_auto_control()
                self.director = None
            new_model = None
            if self.last_mode == "keepaway":
                print("Entering Keep Away")
                self.keepaway_button.config(text="Standard Mode")
                self.yolo_button.config(text="Yolo Mode")
                self.media_pipe_pose_button.config(text="Media Pipe Pose Mode")
                new_model = KeepAwayModel
                self.director = KeepAwayDirector(self.tracker, self.scheduler)
            elif self.last_mode == "yolo":
                print("Entering Yolo")
                self.yolo_button.config(text="Standard Mode")
                self.media_pipe_pose_button.config(text="Media Pipe Pose Mode")
                self.keepaway_button.config(text="Keep Away Mode")
                new_model = YOLOModel
                self.director = ContinuousDirector(self.tracker, self.scheduler)
            elif self.last_mode == "mediapipepose":
                print("Entering Media Pipe Pose")
                self.media_pipe_pose_button.config(text="Standard Mode")
                self.yolo_button.config(text="Yolo Mode")
                self.keepaway_button.config(text="Keep Away Mode")
                new_model = MediaPipePoseModel
                self.director = ContinuousDirector(self.tracker, self.scheduler)
            else:  # "standard"
                print("Entering Media Pipe")
                self.yolo_button.config(text="Yolo Mode")
                self.media_pipe_pose_button.config(text="Media Pipe Pose Mode")
                self.keepaway_button.config(text="Keep Away Mode")
                new_model = MediaPipeModel
                self.director = ContinuousDirector(self.tracker, self.scheduler)
            self.tracker.swap_model(new_model)

        img = self.tracker.create_imagetk()
        if img is not None:
            self.update_video_frame(img)
        self.after(10, self.frame_loop)

    def update_video_frame(self, img: ImageTk.PhotoImage):
        self.video_label.config(image=img)
        # Keep a reference to prevent gc
        # see https://stackoverflow.com/questions/48364168/flickering-video-in-opencv-tkinter-integration
        self.video_label.dumb_image_ref = img  # pyright: ignore[reportAttributeAccessIssue]

    def toggle_continuous_mode(self):
        self.continuous_mode = not self.continuous_mode

        if self.continuous_mode:
            self.cont_mode_label.config(text=ButtonText.CONTINUOUS_MODE_LABEL)
        else:
            self.cont_mode_label.config(text=ButtonText.DISCRETE_MODE_LABEL)

    def toggle_keep_away_mode(self):
        """Switch between normal tracking and Keep-Away game mode."""
        if self.current_mode == "keepaway":
            self.current_mode = "standard"
        else:
            self.current_mode = "keepaway"

    def toggle_media_pipe_pose_mode(self):
        """Switch between normal tracking and Media Pipe Pose mode."""
        if self.current_mode == "mediapipepose":
            self.current_mode = "standard"
        else:
            self.current_mode = "mediapipepose"

    def toggle_yolo_mode(self):
        """Switch between normal tracking and yolo mode."""
        if self.current_mode == "yolo":
            self.current_mode = "standard"
        else:
            self.current_mode = "yolo"

    def toggle_command_mode(self):
        """Toggles command mode between manual mode and automatic mode.
        Disables all other controls when in automatic mode.
        """
        self.manual_mode = not self.manual_mode

        if self.manual_mode:
            self.mode_label.config(text=ButtonText.MANUAL_MODE_LABEL)
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

        self.mode_label.config(text=ButtonText.AUTOMATIC_MODE_LABEL)
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

    def on_close(self):
        print("ugh")
