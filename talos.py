#!/usr/bin/env -S uv run --script

import multiprocessing
import multiprocessing.managers
import os
import sys

# Set the start method for multiprocessing to 'spawn' to avoid fork issues in multi-threaded Qt app
if sys.platform == "darwin" or sys.platform == "linux":
    multiprocessing.set_start_method("spawn", force=True)

from src.arg_parser import ARG_PARSER
from src.logger import configure_logger
from src.talos_app import App
from src.talos_endpoint import TalosEndpoint
from src.utils import terminate

if sys.platform == "win32":
    from pathlib import Path

    pyside_dir = (
        Path(sys.executable).resolve().parent.parent
        / "Lib"
        / "site-packages"
        / "PySide6"
    )
    if pyside_dir.exists():
        os.add_dll_directory(str(pyside_dir))


def create_args():
    args = ARG_PARSER.parse_args()
    if args.debug:
        args.log_level = "DEBUG"
        args.draw_bboxes = True
    return args


def run_server(app: App):
    endpoint = TalosEndpoint(app)
    endpoint.run()


def terminal_interface(args=create_args()):
    from src.interface.textual_tui.main_interface import TextualInterface

    configure_logger(True)
    smm = multiprocessing.managers.SharedMemoryManager()
    interface = TextualInterface(args=args)
    interface.smm = smm
    try:
        interface.run()
    finally:
        terminate(0, 0)


def tk_interface(args=create_args()):
    from src.interface.tk_gui.main_interface import TKInterface

    configure_logger()
    interface = TKInterface(args)
    # TODO: TKinter is incapable of running this much resource intensive tasks
    # in the same thread as the mainloop, so will be resolved later.
    # app = interface.get_app()
    # run_server(app)
    interface.mainloop()


def pyside_interface(args=create_args()):
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from src.interface.pyside_gui.main_interface import PySide6Interface

    configure_logger()
    app = QApplication(sys.argv)

    # Set application font
    font = QFont("Cascadia Code", 10)
    app.setFont(font)

    window = PySide6Interface(args)
    window.show()

    sys.exit(app.exec())


def main() -> None:
    # args = create_args()
    args = create_args()
    # This is a required call for pyinstaller
    # https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#multi-processing
    multiprocessing.freeze_support()

    if args.terminal:
        terminal_interface(args)
    elif args.tkinter:
        tk_interface(args)
    else:
        pyside_interface(args)


if __name__ == "__main__":
    main()
