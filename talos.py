#!/usr/bin/env -S uv run --script

import argparse
import multiprocessing
import multiprocessing.managers

from src.logger import configure_logger
from src.talos_app import App
from src.talos_endpoint import TalosEndpoint
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
        terminal_interface(args)
    else:
        tk_interface(args)


if __name__ == "__main__":
    main()
