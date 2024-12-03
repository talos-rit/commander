from tracking.haar_cascade.basic_tracker import *
from tracking.media_pipe.media_pipe_tracker import *
from directors.continuous_director import *
from directors.discrete_director import *
import argparse
import cv2
from manual_interface import ManualInterface

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=str, default="", help="Path to video file or URL of stream")
    args = parser.parse_args()

    #interface = ManualInterface()
    #interface.launch_user_interface()

    
    tracker = MediaPipeTracker(args.source, "./config.yaml")
    #tracker = BasicTracker(args.source, "./config.yaml")
    #director = DiscreteDirector(tracker, "./config.yaml")
    director = ContinuousDirector(tracker, "./config.yaml")

    while True:
        bounding_box, frame = tracker.capture_frame()

        #Helpful for bounding boxes on screen, this can be removed later
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        if bounding_box is None or frame is None:
            break
        director.process_frame(bounding_box, frame)
    


if __name__ == "__main__":
    main()