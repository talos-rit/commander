import argparse
import multiprocessing

import cv2

from src.directors.continuous_director import ContinuousDirector
from tk_gui.main_interface import TKInterface


def main() -> None:
    # while (not Publisher.connection.is_connected):
    #     print("Waiting to connect...")
    #     time.sleep(5)

    # This is a required call for pyinstaller
    # https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#multi-processing
    multiprocessing.freeze_support()

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
        from tracking.media_pipe.media_pipe_pose_model import MediaPipePoseModel

        tracker = MediaPipePoseModel(None, source=args.source)
        # tracker = MediaPipeTracker(args.source, get_file_path("./config.yaml"))
        # tracker = YOLOTracker(args.source, get_file_path("./config.yaml"))
        # director = DiscreteDirector(tracker, get_file_path("./config.yaml"))
        director = ContinuousDirector(tracker)

        while True:
            bounding_box, frame = tracker.detect_person(False)

            # Helpful for bounding boxes on screen, this can be removed later
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

            if bounding_box is None or frame is None:
                break
            director.process_frame(bounding_box, frame, True)

    interface = TKInterface()
    interface.mainloop()


if __name__ == "__main__":
    main()
