import multiprocessing
import multiprocessing.managers

from src.logger import configure_logger
from src.textual_tui.main_interface import TextualInterface


def main() -> None:
    # This is a required call for pyinstaller
    # https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#multi-processing
    multiprocessing.freeze_support()

    configure_logger(True)
    smm = multiprocessing.managers.SharedMemoryManager()
    interface = TextualInterface()
    interface.smm = smm
    interface.run()


if __name__ == "__main__":
    main()
