import argparse


def _create_arg_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-t",
        "--terminal",
        action="store_true",
        help="Use the terminal (textual) interface instead of the Tk GUI",
    )
    parser.add_argument(
        "-tk",
        "--tkinter",
        action="store_true",
        help="Use the Tkinter GUI instead of the PySide6 GUI",
    )
    parser.add_argument(
        "--draw-bboxes",
        action="store_true",
        help="Draw bounding boxes around detected speakers in the video feed.",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Enable debug mode, which sets the log level to DEBUG and sets draw_bboxes to True",
    )
    parser.add_argument(
        "--connection",
        type=str,
        help="Specify the hostname of a connection to connect to on startup (e.g. 'unctalos.student.rit.edu')",
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Specify the model to use for speaker detection and tracking (e.g. 'yolov8m'). This doesn't do anything if the connection argument is not provided",
    )
    parser.add_argument(
        "--control-mode",
        type=str,
        choices=["manual", "auto"],
        help="Specify the initial control mode (manual or auto). This doesn't do anything if the connection argument is not provided",
    )
    parser.add_argument(
        "--director",
        default="continuous",
        choices=["continuous", "discrete"],
        type=str,
        help="Specify the director to use for robot control (e.g. 'continuous'). This doesn't do anything if the connection argument is not provided",
    )
    return parser


ARG_PARSER = _create_arg_parser()
