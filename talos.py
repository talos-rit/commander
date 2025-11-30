import argparse
import multiprocessing
import multiprocessing.managers
import multiprocessing.shared_memory

from src.textual_tui.main_interface import Interface
from src.tk_gui.main_interface import TKInterface


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
        "-t",
        "--terminal",
        action="store_true",
        help="Path to video file or URL of stream",
    )
    args = parser.parse_args()

    if args.terminal:
        smm = multiprocessing.managers.SharedMemoryManager()
        interface = Interface()
        interface.smm = smm
        interface.run()
    else:
        interface = TKInterface()
        interface.mainloop()


if __name__ == "__main__":
    main()
