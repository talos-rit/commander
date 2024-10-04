"""
Example file/stubbed to show how publisher is used.
"""

#from publisher import Publisher
import tkinter

#Publisher.rotate(45)

UP = "up"

class ManualInterface:
    """
    Representation of a manual interface used to control 
    the robotic arm which holds the camera.
    """
    
    def __init__(self):
        """Constructor sets up tkinter manual interface and launches it
        """
        
        # directional strings for movement commands
        
        self.up = "up"
        self.down = "down"
        self.left = "left"
        self.right= "right"
        
        
         # unicode arrow symbols
        
        self.up_arrow = "\u2191"
        self.down_arrow = "\u2193"
        self.left_arrow = "\u2190"
        self.right_arrow = "\u2192"
        
        self.rootWindow = tkinter.Tk()
        self.rootWindow.title("Talos Manual Interface")
        
        self.pressed_keys = {} # keeps track of keys which are pressed down
        self.move_delay_ms = 10
        
        # setting up manual vs automatic control toggle
        
        self.manual_mode = True  # True for manual, False for computer vision
        self.mode_label = tkinter.Label(self.rootWindow, text = "Mode: Manual", font = ("Cascadia Code", 12))
        self.mode_label.grid(row = 0, column = 4)
           
        self.toggle_button = tkinter.Button(self.rootWindow, text = "Switch to Automatic Control", font = ("Cascadia Code", 12), command = self.toggle_command_mode)
        self.toggle_button.grid(row = 2, column = 4, padx = 50)
        
        
        # setting up directional buttons
        
        self.up_button = tkinter.Button(self.rootWindow, text = self.up_arrow, height = 2, width = 10, font = ("Cascadia Code", 16))
        self.up_button.grid(row = 1, column = 1, padx = 10, pady = 10)
        
        self.bind_button(self.up_button, self.up)

        self.down_button = tkinter.Button(self.rootWindow, text = self.down_arrow, height = 2, width = 10, font = ("Cascadia Code", 16))
        self.down_button.grid(row = 3, column = 1, padx = 10, pady = 10)

        self.bind_button(self.down_button, self.down)

        self.left_button = tkinter.Button(self.rootWindow, text = self.left_arrow, height = 2, width = 10, font = ("Cascadia Code", 16))
        self.left_button.grid(row = 2, column = 0, padx = 10, pady = 10)
        
        self.bind_button(self.left_button, self.left)

        self.right_button = tkinter.Button(self.rootWindow, text = self.right_arrow, height = 2, width = 10, font = ("Cascadia Code", 16))
        self.right_button.grid(row = 2, column = 2, padx = 10, pady = 10)
        
        self.bind_button(self.right_button, self.right)
        
        self.setup_keyboard_controls()
        
        
    def setup_keyboard_controls(self):
        """ does the tedious work of binding the keyboard arrow keys to the button controls
        """
        self.rootWindow.bind("<KeyPress-Up>", lambda event: self.start_move(self.up))
        self.rootWindow.bind("<KeyRelease-Up>", lambda event: self.stop_move(self.up))
        
        self.rootWindow.bind("<KeyPress-Down>", lambda event: self.start_move(self.down))
        self.rootWindow.bind("<KeyRelease-Down>", lambda event: self.stop_move(self.down))
        
        self.rootWindow.bind("<KeyPress-Left>", lambda event: self.start_move(self.left))
        self.rootWindow.bind("<KeyRelease-Left>", lambda event: self.stop_move(self.left))
        
        self.rootWindow.bind("<KeyPress-Right>", lambda event: self.start_move(self.right))
        self.rootWindow.bind("<KeyRelease-Right>", lambda event: self.stop_move(self.right))
        
    
    def bind_button(self, button, direction):
        """ shortens the constructor by binding button up/down presses

        Args:
            button (tkinter.Button): button to bind with press and release functions
            direction (string): global variables for directional commands are provided at the top of this file
        """
        
        button.bind("<ButtonPress>", lambda event: self.start_move(direction))
        button.bind("<ButtonRelease>", lambda event: self.stop_move(direction))
    
    
    def start_move(self, direction):
        """ moves the robotic arm a static number of degrees per second

        Args:
            direction (string): global variables for directional commands are provided at the top of this file 
        """
        
        if self.manual_mode:
            if direction not in self.pressed_keys:
                
                self.pressed_keys[direction] = True
                self.keep_moving(direction)
    
    
    def stop_move(self, direction):
        """ stops a movement going the current direction

        Args:
            direction (_string_): global variables for directional commands are provided at the top of this file 
        """
        if self.manual_mode:
            if direction in self.pressed_keys:
                self.pressed_keys.pop(direction)
    
    def keep_moving(self, direction):
        """ continuously allows moving to continue as controls are pressed and stops them once released

        Args:
            direction (_type_): global variables for directional commands are provided at the top of this file
        """
        if direction in self.pressed_keys:
            
            print("Moving " + direction) # replace with movement functionality
            
            self.rootWindow.after(self.move_delay_ms, lambda: self.keep_moving(direction)) # lambda used as function reference
        
    def launch_user_interface(self):
        self.rootWindow.mainloop()
    
    def toggle_command_mode(self):
        
        self.manual_mode = not self.manual_mode
        
        if(self.manual_mode):
            self.mode_label.config(text = "Mode: Manual")
            self.toggle_button.config(text = "Switch to Automatic Control")
            
            self.up_button.config(state = "normal")
            self.down_button.config(state = "normal")
            self.left_button.config(state = "normal")
            self.right_button.config(state = "normal")
            
            self.pressed_keys = {}
            
        else:
            self.mode_label.config(text = "Mode: Automatic")
            self.toggle_button.config(text = "Switch to Manual Control")
            
            self.up_button.config(state = "disabled")
            self.down_button.config(state = "disabled")
            self.left_button.config(state = "disabled")
            self.right_button.config(state = "disabled")
            
            self.pressed_keys = {self.up, self.down, self.left, self.right}


interface = ManualInterface()
interface.launch_user_interface()