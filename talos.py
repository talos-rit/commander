import argparse
import multiprocessing
import multiprocessing.managers

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
    else:
        interface = TKInterface()
        interface.mainloop()


if __name__ == "__main__":
    main(create_args())
