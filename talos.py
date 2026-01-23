import argparse
import multiprocessing
import multiprocessing.managers
import sys

from loguru import logger

from src.textual_tui.main_interface import TextualInterface
from src.tk_gui.main_interface import TKInterface


def configure_logger(remove_existing: bool = False):
    if remove_existing:
        # Shuts up console output for loguru
        logger.remove()
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
    else:
        configure_logger()
        interface = TKInterface()
        interface.mainloop()


if __name__ == "__main__":
    main(create_args())
