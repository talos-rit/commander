from enum import Enum
from publisher import Publisher
from tracking.media_pipe.media_pipe_tracker import *
from tracking.media_pipe.media_pipe_pose import *
from directors.continuous_director import *
from directors.discrete_director import *
import tkinter
import time
from threading import Thread
from PIL import Image, ImageTk
from threading import Thread


class Direction(Enum):
    """ Directional Enum for interface controls

    """
    UP = 1
    DOWN = 2
    LEFT = 3
    RIGHT = 4

    def __int__(self):
        """
        Used for casting Enum object to integer
        """
        return self.value


class ManualInterface:
    """
    Representation of a manual interface used to control 
    the robotic arm which holds the camera.
    """
    
    def __init__(self):
        """ Constructor sets up tkinter manual interface, including buttons and labels
        """
        
         # unicode button symbols
        
        self.up_arrow = "\u2191"
        self.down_arrow = "\u2193"
        self.left_arrow = "\u2190"
        self.right_arrow = "\u2192"
        self.home = "🏠"
        self.switch = " ⤭ "

        # button labels
        self.MOVEMENT_MODE = "Movement Mode: "
        self.CONTINUOUS_MODE_LABEL = self.MOVEMENT_MODE + "Continuous"
        self.DISCRETE_MODE_LABEL = self.MOVEMENT_MODE + "Discrete"
        self.CONTROL_MODE = "Control Mode: "
        self.MANUAL_MODE_LABEL = self.CONTROL_MODE + "Manual"
        self.AUTOMATIC_MODE_LABEL = self.CONTROL_MODE + "Automatic"
                
        self.rootWindow = tkinter.Tk()
        self.rootWindow.title("Talos Manual Interface")
        
        self.pressed_keys = {} # keeps track of keys which are pressed down
        self.move_delay_ms = 300 # time inbetween each directional command being sent while directional button is depressed
        
        # setting up manual vs automatic control toggle
        
        self.manual_mode = True  # True for manual, False for computer vision
        
        self.mode_label = tkinter.Label(self.rootWindow, text = self.MANUAL_MODE_LABEL, font = ("Cascadia Code", 12))
        self.mode_label.grid(row = 2, column = 4)
           
        self.toggle_button = tkinter.Button(
            self.rootWindow,
            text = self.switch,
            font = ("Cascadia Code", 16, "bold"),
            command = self.toggle_command_mode
        )
        self.toggle_button.grid(row = 2, column = 5, padx = 10)

        # Setup up continuous/discrete toggle

        self.continuous_mode = True

        self.cont_mode_label = tkinter.Label(self.rootWindow, text = self.CONTINUOUS_MODE_LABEL, font = ("Cascadia Code", 12))
        self.cont_mode_label.grid(row = 1, column = 4)

        self.cont_toggle_button = tkinter.Button(
            self.rootWindow,
            text = self.switch,
            font = ("Cascadia Code", 16, "bold"),
            command = self.toggle_continuous_mode
        )
        self.cont_toggle_button.grid(row = 1, column = 5, padx = 10)
        
        # setting up home button
        
        self.home_button = tkinter.Button(self.rootWindow, text = self.home, font = ("Cascadia Code", 16), command = self.move_home)
        self.home_button.grid(row = 3, column = 4)
        
        # setting up directional buttons
        
        self.up_button = tkinter.Button(self.rootWindow, text = self.up_arrow, height = 2, width = 10, font = ("Cascadia Code", 16, "bold"))
        self.up_button.grid(row = 1, column = 1, padx = 10, pady = 10)
        
        self.bind_button(self.up_button, Direction.UP)

        self.down_button = tkinter.Button(self.rootWindow, text = self.down_arrow, height = 2, width = 10, font = ("Cascadia Code", 16, "bold"))
        self.down_button.grid(row = 3, column = 1, padx = 10, pady = 10)

        self.bind_button(self.down_button, Direction.DOWN)

        self.left_button = tkinter.Button(self.rootWindow, text = self.left_arrow, height = 2, width = 10, font = ("Cascadia Code", 16, "bold"))
        self.left_button.grid(row = 2, column = 0, padx = 10, pady = 10)
        
        self.bind_button(self.left_button, Direction.LEFT)

        self.right_button = tkinter.Button(self.rootWindow, text = self.right_arrow, height = 2, width = 10, font = ("Cascadia Code", 16, "bold"))
        self.right_button.grid(row = 2, column = 2, padx = 10, pady = 10)
        
        self.bind_button(self.right_button, Direction.RIGHT)
        
        self.setup_keyboard_controls()

        self.last_key_presses = {}

        #Setting up integrated video
        # Create a label that will display video frames.
        self.video_label = tkinter.Label(self.rootWindow)
        #This line ensures it stays on the top of the manual interface and centers it in the  middle
        self.video_label.grid(row=0, column=0, columnspan=6, padx=10, pady=10, sticky="nsew")
        
        # Flags for director loop
        self.is_director_running = False
        self.director_thread = None

        self.start_director_thread()
        
        
    def setup_keyboard_controls(self):
        """ Does the tedious work of binding the keyboard arrow keys to the button controls.
        """
        self.rootWindow.bind("<KeyPress-Up>", lambda event: self.start_move(Direction.UP))
        self.rootWindow.bind("<KeyRelease-Up>", lambda event: self.stop_move(Direction.UP))
        
        self.rootWindow.bind("<KeyPress-Down>", lambda event: self.start_move(Direction.DOWN))
        self.rootWindow.bind("<KeyRelease-Down>", lambda event: self.stop_move(Direction.DOWN))
        
        self.rootWindow.bind("<KeyPress-Left>", lambda event: self.start_move(Direction.LEFT))
        self.rootWindow.bind("<KeyRelease-Left>", lambda event: self.stop_move(Direction.LEFT))
        
        self.rootWindow.bind("<KeyPress-Right>", lambda event: self.start_move(Direction.RIGHT))
        self.rootWindow.bind("<KeyRelease-Right>", lambda event: self.stop_move(Direction.RIGHT))
        
        
    def bind_button(self, button, direction):
        """ Shortens the constructor by binding button up/down presses.

        Args:
            button (tkinter.Button): button to bind with press and release functions
            direction (string): global variables for directional commands are provided at the top of this file
        """
        
        button.bind("<ButtonPress>", lambda event: self.start_move(direction))
        button.bind("<ButtonRelease>", lambda event: self.stop_move(direction))
    
    def start_move(self, direction):
        """ Moves the robotic arm a static number of degrees per second.

        Args:
            direction (string): global variables for directional commands are provided at the top of this file 
        """
        if self.manual_mode:

            self.last_key_presses[int(direction)] = time.time()

            if direction not in self.pressed_keys:
                self.pressed_keys[direction] = True
                
                self.change_button_state(direction, "sunken")

                if not self.continuous_mode:
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
                else:
                    self.keep_moving(direction)
                   
    def stop_move(self, direction):
        """ Stops a movement going the current direction.

        Args:
            direction (string): global variables for directional commands are provided at the top of this file 
        """
        if self.manual_mode:
            if direction in self.pressed_keys:
                if int(direction) in self.last_key_presses:
                    last_pressed_time = self.last_key_presses[int(direction)]

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
                        new_last_pressed_time = self.last_key_presses[int(direction)]
                       
                        # Check if the key has been pressed or if the times are the same
                        if new_last_pressed_time == last_pressed_time:
                            self.pressed_keys.pop(direction)
                            self.change_button_state(direction, "raised")

                    # Start the thread
                    thread = Thread(target=stop_func)
                    thread.start()
                else:
                    self.pressed_keys.pop(direction)
                    self.change_button_state(direction, "raised")
    
    
    def change_button_state(self, direction, depression):
        """ Changes button state to sunken or raised based on input depression argument.

        Args:
            direction (enum): the directional button to change.
            depression (string): "raised" or "sunken", the depression state to change to.
        """
        
        match direction:
            case Direction.UP:
                self.up_button.config(relief = depression)
            case Direction.DOWN:
                self.down_button.config(relief = depression)
            case Direction.LEFT:
                self.left_button.config(relief = depression)
            case Direction.RIGHT:
                self.right_button.config(relief = depression)

        if self.continuous_mode:
            # Send a continuous polar pan STOP if no key is pressed
            if len(self.pressed_keys) == 0:
                Publisher.polar_pan_continuous_stop()
                print("Polar pan cont STOP")

    
    def keep_moving(self, direction):
        """ Continuously allows moving to continue as controls are pressed and stops them once released by recursively calling this function while
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

            print(f"Polar pan cont Azimuth: {moving_azimuth} Altitude: {moving_altitude}")

            Publisher.polar_pan_continuous_start(
                moving_azimuth=moving_azimuth,
                moving_altitude=moving_altitude
            )
       
        if self.continuous_mode:
            self.rootWindow.after(self.move_delay_ms, lambda: self.keep_moving(direction)) # lambda used as function reference to execute when required
        
        
    def move_home(self):
        """ Moves the robotic arm from its current location to its home position
        """
        print("Moving home")
        Publisher.home(1000) # sends a command to move to home via the publisher
    
    
    def launch_user_interface(self):
        """ Launches user interface on demand.
        """
        self.rootWindow.mainloop()

    def director_loop(self):
        """ Launches the tracker and director.
        """
        tracker = MediaPipePose(source="", config_path="./config.yaml")

        director = ContinuousDirector(tracker, "./config.yaml", self.video_label)

        while True:
            bounding_box, frame = tracker.capture_frame()

            if bounding_box is None or frame is None:
                continue
            director.process_frame(bounding_box, frame, self.is_director_running, True)


    def start_director_thread(self): 
        if self.director_thread is None or not self.director_thread.is_alive():
            self.director_thread = Thread(target=self.director_loop, daemon=True)
            self.director_thread.start()


    def toggle_continuous_mode(self):
        self.continuous_mode = not self.continuous_mode

        if self.continuous_mode:
            self.cont_mode_label.config(text = self.CONTINUOUS_MODE_LABEL)
        else:
            self.cont_mode_label.config(text = self.DISCRETE_MODE_LABEL)
    
    
    def toggle_command_mode(self):
        """ Toggles command mode between manual mode and automatic mode.
            Disables all other controls when in automatic mode.
        """
        self.manual_mode = not self.manual_mode
        
        if self.manual_mode:
            self.mode_label.config(text = self.MANUAL_MODE_LABEL)
            
            self.up_button.config(state = "normal")
            self.down_button.config(state = "normal")
            self.left_button.config(state = "normal")
            self.right_button.config(state = "normal")
            
            self.home_button.config(state = "normal")
            
            self.is_director_running = False
            self.pressed_keys = {}
            
        else:
            self.mode_label.config(text = self.AUTOMATIC_MODE_LABEL)
            
            self.up_button.config(state = "disabled")
            self.down_button.config(state = "disabled")
            self.left_button.config(state = "disabled")
            self.right_button.config(state = "disabled")
            
            self.home_button.config(state = "disabled")
            
            self.pressed_keys = {Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT}
            self.is_director_running = True
