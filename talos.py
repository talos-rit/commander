import argparse
import multiprocessing
import multiprocessing.managers
import os
import sys

from src.logger import configure_logger
from src.textual_tui.main_interface import TextualInterface
from src.tk_gui.main_interface import TKInterface


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


def main(args) -> None:
    # This is a required call for pyinstaller
    # https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#multi-processing
    multiprocessing.freeze_support()

    if args.terminal:
        configure_logger(True)
        smm = multiprocessing.managers.SharedMemoryManager()
        interface = TextualInterface()
        interface.smm = smm
        interface.run()
    elif args.tkinter:
        configure_logger()
        interface = TKInterface()
        interface.mainloop()
    else:
        app = QApplication(sys.argv)
        
        # Set application font
        font = QFont("Cascadia Code", 10)
        app.setFont(font)
        
        window = PySide6Interface()
        window.show()
        
        sys.exit(app.exec())

if __name__ == "__main__":
    main(create_args())
