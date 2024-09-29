from tracking.basic_tracker import *
from director.basic_director import *
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=str, default="", help="Path to video file or URL of stream")
    args = parser.parse_args()

    tracker = BasicTracker(args.source)
    director = BasicDirector(tracker)

    while True:
        frame = tracker.capture_frame()
        if frame is None:
            break
        director.process_frame(frame)

if __name__ == "__main__":
    main()