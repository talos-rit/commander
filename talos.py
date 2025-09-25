import argparse

import cv2

from directors.continuous_director import ContinuousDirector
from manual_interface import ManualInterface
from tracking.media_pipe.media_pipe_pose import MediaPipePose


def main():
    # while (not Publisher.connection.is_connected):
    #     print("Waiting to connect...")
    #     time.sleep(5)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", type=str, default="", help="Path to video file or URL of stream"
    )
    parser.add_argument(
        "--no_interface",
        type=str,
        default="false",
        help="Path to video file or URL of stream",
    )
    args = parser.parse_args()

    if args.no_interface == "true":
        tracker = MediaPipePose(None, source=args.source)
        # tracker = MediaPipeTracker(args.source, get_file_path("./config.yaml"))
        # tracker = YOLOTracker(args.source, get_file_path("./config.yaml"))
        # director = DiscreteDirector(tracker, get_file_path("./config.yaml"))
        director = ContinuousDirector(tracker)

        while True:
            bounding_box, frame = tracker.capture_frame(False)

            # Helpful for bounding boxes on screen, this can be removed later
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

            if bounding_box is None or frame is None:
                break
            director.process_frame(bounding_box, frame, True)

    else:
        interface = ManualInterface()
        interface.launch_user_interface()


if __name__ == "__main__":
    main()
