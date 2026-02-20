#!/usr/bin/env -S uv run --script

import argparse
import multiprocessing
import multiprocessing.managers
import os
import sys

# Set the start method for multiprocessing to 'spawn' to avoid fork issues in multi-threaded Qt app
if sys.platform == "darwin" or sys.platform == "linux":
    multiprocessing.set_start_method("spawn", force=True)

from src.logger import configure_logger
from src.talos_app import App
from src.talos_endpoint import TalosEndpoint
from src.textual_tui.main_interface import TextualInterface
from src.tk_gui.main_interface import TKInterface, terminate

from src.pyside_gui.main_interface import PySide6Interface
if sys.platform == "win32":
    os.environ["PATH"] += os.pathsep + r".venv\Lib\site-packages\PySide6"

    os.add_dll_directory(r".venv\Lib\site-packages\PySide6")
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont


def create_args():
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
    return parser.parse_args()


def run_server(app: App):
    endpoint = TalosEndpoint(app)
    endpoint.run()


def run_server(app: App):
    endpoint = TalosEndpoint(app)
    endpoint.run()


def terminal_interface(args=None):
    configure_logger(True)
    smm = multiprocessing.managers.SharedMemoryManager()
    interface = TextualInterface()
    interface.smm = smm
    interface.run()


def tk_interface(args=None):
    configure_logger()
    interface = TKInterface()
    # TODO: TKinter is incapable of running this much resource intensive tasks
    # in the same thread as the mainloop, so will be resolved later.
    # app = interface.get_app()
    # run_server(app)
    interface.mainloop()


def main() -> None:
    args = create_args()
    # This is a required call for pyinstaller
    # https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#multi-processing
    multiprocessing.freeze_support()

    if args.terminal:
        configure_logger(True)
        smm = multiprocessing.managers.SharedMemoryManager()
        interface = TextualInterface()
        interface.smm = smm
        interface.run()
    else:
        configure_logger()
        interface = TKInterface()
        interface.mainloop()


if __name__ == "__main__":
    main()
