import time
import yaml
import cv2
import random
from PIL import Image, ImageTk

from tracking.tracker import Tracker
from directors.base_director import BaseDirector
from publisher import Publisher
from tracking.squid_game.squid_game_tracker import *


NUM_SKIP_FRAMES = 15


class SquidGameDirector(BaseDirector):
    # The director class is responsible for processing the frames captured by the tracker
    def __init__(self, tracker : Tracker, config_path, video_label):
        super().__init__(config_path)
        self.green_light = False # bool to ensure the director is not running when the green light is on
        self.freeze_frame = None # frame to freeze the camera on when the green light is on
        self.gray_freeze_frame = None # grayscale version of the freeze frame
        self.video_label = video_label #Label on the manual interface that shows the video feed with bounding boxes

        # Green Light state machine
        self.green_light_state = "IDLE" # State machine for the green light sequence ["IDLE", "MOVING_DOWN", "WAITING"]
        self.green_light_timer = None # Timer for the green light sequence steps
        self.green_light_wait_duration = None # Random wait duration for the green light sequence
        self.down_move_duration = 0.7 # Duration for moving down

        # Red Light state machine
        self.red_light_state = "DETECTING" # State machine for red light ["MOVING_UP", "DETECTING"]
        self.red_light_timer = time.time() # Start the timer for the initial detection phase
        self.red_light_duration = 5 # Default duration for detection phase, will be randomized
        self.up_move_start_time = None # Timer for the upward movement
        self.up_move_duration = self.down_move_duration # Match upward movement duration to downward
        self.skipped_frames = 0

        print("[DEBUG] SquidGameDirector initialized. Starting in RED LIGHT phase (DETECTING state).")

    def change_video_frame(self, frame, is_interface_running):
        # Assuming is_interface_running is always True based on usage,
        # but keeping the check in case it's used differently elsewhere.
        if is_interface_running:
            # Once all drawings and processing are done, update the display.
            # Convert from BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)

            # Set desired dimensions (adjust these values as needed)
            desired_width = 640
            desired_height = 480
            pil_image = pil_image.resize((desired_width, desired_height), Image.Resampling.LANCZOS)

            imgtk = ImageTk.PhotoImage(image=pil_image)

            # Update the label
            self.video_label.after(0, lambda imgtk=imgtk: self.update_video_label(imgtk))

    def update_video_label(self, imgtk):
        self.video_label.config(image=imgtk)
        self.video_label.image = imgtk

    # This method is called to process each frame, bounding_boxes is a list of x1, y1, x2, y2 coordinates
    def process_frame(self, bounding_boxes : list, frame, is_director_running):
        current_time = time.time()

        # If green light is on, run the green light sequence
        if self.green_light == True:
            # Display the live frame without boxes during the green light sequence
            display_frame = frame.copy()
            # Optional: Draw green light indicator
            # cv2.putText(display_frame, "GREEN LIGHT", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)
            self.change_video_frame(display_frame, True)

            if self.green_light_state == "IDLE":
                # Start the sequence
                print("[DEBUG] Green Light Phase: Starting sequence. State -> MOVING_DOWN")
                Publisher.polar_pan_continuous_start(0, -1) # Move the camera downwards
                self.green_light_timer = current_time
                self.green_light_state = "MOVING_DOWN"

            elif self.green_light_state == "MOVING_DOWN":
                # Check if downward movement duration has passed
                if current_time - self.green_light_timer >= self.down_move_duration:
                    print(f"[DEBUG] Green Light Phase: Stopping downward movement ({self.down_move_duration}s). State -> WAITING")
                    Publisher.polar_pan_continuous_stop() # Stop the camera
                    self.green_light_wait_duration = random.randint(1, 2) + random.random() # Set random wait time
                    print(f"[DEBUG] Green Light Phase: Set random wait duration: {self.green_light_wait_duration:.2f}s")
                    self.green_light_timer = current_time # Reset timer for waiting period
                    self.green_light_state = "WAITING"

            elif self.green_light_state == "WAITING":
                # Check if the random wait duration has passed
                if current_time - self.green_light_timer >= self.green_light_wait_duration:
                    print(f"[DEBUG] Green Light Phase: Wait duration ({self.green_light_wait_duration:.2f}s) ended.")
                    # --- Transition to Red Light ---
                    Publisher.polar_pan_continuous_stop() # Ensure stopped before capturing frame

                    print("[DEBUG] Transitioning to RED LIGHT phase. State -> MOVING_UP")
                    Publisher.polar_pan_continuous_start(0, 1) # Start moving the camera upwards
                    self.up_move_start_time = current_time # Start timer for upward movement
                    self.green_light = False # End the green light phase
                    self.green_light_state = "IDLE" # Reset green light state machine
                    self.red_light_state = "MOVING_UP" # Set red light state to moving up
                    # Red light detection duration/timer will be set after upward movement finishes

        # If the green light is off (RED LIGHT phase)
        else:
            # --- Red Light State Machine ---
            if self.red_light_state == "MOVING_UP":
                self.skipped_frames = 0
                # Check if upward movement duration has passed
                if current_time - self.up_move_start_time >= self.up_move_duration:
                    print(f"[DEBUG] Red Light Phase: Stopping upward movement ({self.up_move_duration}s). State -> DETECTING")
                    Publisher.polar_pan_continuous_stop() # Stop the upward movement
                    self.red_light_state = "DETECTING" # Transition to detection state
                    # Set random duration for the detection phase
                    self.red_light_duration = random.randint(4, 10) + random.random()
                    self.red_light_timer = current_time # Start the timer for the detection phase
                    print(f"[DEBUG] Red Light Phase (DETECTING): Started. Duration: {self.red_light_duration:.2f}s")
                    #time.sleep(.5)

                    self.freeze_frame = frame.copy() # Capture the current frame for red light phase
                    print("[DEBUG] Captured freeze frame.")
                    # Convert freeze frame to grayscale once
                    if self.freeze_frame is not None:
                         self.gray_freeze_frame = cv2.cvtColor(self.freeze_frame, cv2.COLOR_BGR2GRAY)
                         print("[DEBUG] Converted freeze frame to grayscale.")
                    # Process this frame immediately using detection logic below
                else:
                    # Still moving up, display the freeze frame (without boxes)
                    if self.freeze_frame is not None:
                        self.change_video_frame(self.freeze_frame.copy(), True)
                    else: # Should not happen if transition logic is correct, but fallback
                         self.change_video_frame(frame.copy(), True)
                    return # Skip detection logic while moving up

            # State is DETECTING (or initial state before first green light)
            if self.red_light_state == "DETECTING":
                # Check if it's time to switch back to Green Light
                # Ensure red_light_timer is set (won't be None after first MOVING_UP -> DETECTING transition)
                self.skipped_frames += 1

                if self.skipped_frames == NUM_SKIP_FRAMES - 1:
                    self.freeze_frame = frame.copy()
                    self.gray_freeze_frame = cv2.cvtColor(self.freeze_frame, cv2.COLOR_BGR2GRAY)

                if self.red_light_timer is not None and current_time - self.red_light_timer >= self.red_light_duration:
                    print(f"[DEBUG] Red Light Phase (DETECTING): Duration ({self.red_light_duration:.2f}s) ended.")
                    # --- Transition back to Green Light ---
                    print("[DEBUG] Transitioning back to GREEN LIGHT phase.")
                    self.green_light = True
                    self.freeze_frame = None # Clear the freeze frame
                    self.gray_freeze_frame = None # Clear the grayscale freeze frame
                    print("[DEBUG] Cleared freeze frame and grayscale version.")
                    self.red_light_timer = None # Reset red light timer
                    self.red_light_state = "DETECTING" # Reset state for next red light phase
                    # Display the current frame briefly before green light movement starts
                    self.change_video_frame(frame.copy(), True)
                    return # Skip the rest of the processing for this frame

                # --- Continue with Red Light Detection Logic ---
                # Ensure freeze_frame and its grayscale version are available
                elif self.freeze_frame is not None and self.gray_freeze_frame is not None:
                    # Convert current frame to grayscale for comparison
                    gray_current_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                    # Parameters for movement detection
                    pixel_diff_threshold = 40
                    movement_area_ratio_threshold = 0.2

                    processed_frame = frame.copy() # Work on a copy to draw boxes
                    movement_detected_in_frame = False

                    frame_height, frame_width = self.gray_freeze_frame.shape[:2]
                    current_frame_height, current_frame_width = gray_current_frame.shape[:2]

                    for box in bounding_boxes:
                        x1, y1, x2, y2 = map(int, box)
                        w = x2 - x1
                        h = y2 - y1

                        # Validate coordinates and dimensions against both frames
                        if w <= 0 or h <= 0 or \
                           x1 < 0 or y1 < 0 or \
                           x2 > frame_width or y2 > frame_height or \
                           x2 > current_frame_width or y2 > current_frame_height:
                            continue

                        try:
                            roi_freeze = self.gray_freeze_frame[y1:y2, x1:x2]
                            roi_current = gray_current_frame[y1:y2, x1:x2]
                        except IndexError:
                            continue

                        if roi_freeze.size == 0 or roi_current.size == 0 or roi_freeze.shape != roi_current.shape:
                             continue

                        diff = cv2.absdiff(roi_freeze, roi_current)
                        _, thresh = cv2.threshold(diff, pixel_diff_threshold, 255, cv2.THRESH_BINARY)
                        changed_pixels_count = cv2.countNonZero(thresh)
                        roi_area = w * h
                        if roi_area == 0: continue
                        changed_ratio = changed_pixels_count / roi_area

                        if changed_ratio > movement_area_ratio_threshold:
                            if not movement_detected_in_frame:
                                if self.skipped_frames > NUM_SKIP_FRAMES:
                                    print(f"[DEBUG] Red Light Phase (DETECTING): Movement detected! Box: {(x1, y1, x2, y2)}, Change Ratio: {changed_ratio:.4f}")
                                    movement_detected_in_frame = True
                                    cv2.rectangle(processed_frame, (x1, y1), (x2, y2), (0, 0, 255), 2) # Red
                                else:
                                    print("SKIPPING FRAME")
                                    cv2.rectangle(processed_frame, (x1, y1), (x2, y2), (0, 255, 0), 2) # Green
                        else:
                            cv2.rectangle(processed_frame, (x1, y1), (x2, y2), (0, 255, 0), 2) # Green

                    # Update the video frame with detection results
                    self.change_video_frame(processed_frame, True)

                else:
                    # Initial state: freeze_frame is None (before first green light)
                    # Or if something went wrong setting freeze_frame
                    if self.freeze_frame is None and self.red_light_timer is None:
                         # This condition might be less relevant now with the state machine handling init
                         print("[DEBUG] Initial state (Red Light Phase): No freeze frame yet. Displaying current boxes.")
                    elif self.freeze_frame is None:
                         print("[WARN] Red Light Phase (DETECTING): freeze_frame is None. Displaying current boxes.")


                    processed_frame = frame.copy()
                    frame_height, frame_width = processed_frame.shape[:2]
                    for box in bounding_boxes:
                        x1, y1, x2, y2 = map(int, box)
                        w = x2 - x1
                        h = y2 - y1
                        if w > 0 and h > 0 and x1 >= 0 and y1 >= 0 and x2 <= frame_width and y2 <= frame_height:
                           cv2.rectangle(processed_frame, (x1, y1), (x2, y2), (0, 255, 0), 2) # Green

                    self.change_video_frame(processed_frame, True) # Update the video frame

