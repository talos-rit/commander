from tracking.haar_cascade.basic_tracker import *
from tracking.media_pipe.media_pipe_tracker import *
from directors.basic_director import *
import argparse
import cv2
from manual_interface import ManualInterface

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=str, default="", help="Path to video file or URL of stream")
    args = parser.parse_args()

    interface = ManualInterface()
    interface.launch_user_interface()

    
    tracker = MediaPipeTracker(args.source)
    director = BasicDirector(tracker, "./config.yaml")

    while True:
        frame = tracker.capture_frame()

        #Helpful for bounding boxes on screen, this can be removed later
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        if frame is None:
            break
        director.process_frame(frame)
    


if __name__ == "__main__":
    main()