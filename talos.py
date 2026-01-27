import argparse
import multiprocessing
import multiprocessing.managers
import os
import sys

from loguru import logger

from src.textual_tui.main_interface import TextualInterface
from src.tk_gui.main_interface import TKInterface
from src.pyside_gui.main_interface import PySide6Interface
if sys.platform == "win32":
    os.add_dll_directory(".venv\Lib\site-packages\PySide6")
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont


def configure_logger():
    logger.add(
        ".log/log_{time}.log",
        enqueue=True,
        retention="10 days",
        backtrace=True,
        diagnose=True,
    )

    class StreamToLoguru:
        def write(self, message):
            message = message.strip()
            if message:
                logger.info(message)

        def flush(self):
            pass  # Needed for file-like API

    sys.stdout = StreamToLoguru()
    sys.stderr = StreamToLoguru()


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
        smm = multiprocessing.managers.SharedMemoryManager()
        interface = TextualInterface()
        interface.smm = smm
        interface.run()
    elif args.tkinter:
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
    configure_logger()
    main(create_args())
