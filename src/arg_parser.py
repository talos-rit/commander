
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
        '--draw-bboxes',
        action='store_true',
        help='Draw bounding boxes around detected speakers in the video feed.',
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Enable debug mode, which sets the log level to DEBUG and sets draw_bboxes to True",
    )
    return parser

ARG_PARSER = _create_arg_parser()