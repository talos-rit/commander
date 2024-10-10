from tracking.tracker import Tracker

class BasicDirector:
    # The director class is responsible for processing the frames captured by the tracker
    def __init__(self, tracker : Tracker):
        self.tracker = tracker

    # This method is called to process each frame
    def process_frame(self, frame : list):
    # Do something with the frame
        print(frame)
