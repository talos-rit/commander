import os
from typing import Callable

from loguru import logger
from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)

from ...utils import get_file_path
from ..path import BACKUP_DIR, ROBOT_CONFIGS_PATH
from ..schema.robot import RobotConfigs


def take_backup() -> str:
    import src.config as config

    robot_configs = config.ROBOT_CONFIGS.copy()
    path = get_file_path(os.path.join(BACKUP_DIR, ROBOT_CONFIGS_PATH + ".backup"))
    if os.path.exists(path):
        ind = 1
        while os.path.exists(path + str(ind)):
            ind += 1
        path += str(ind)
    with open(path, "w") as f:
        import yaml

        yaml.safe_dump(robot_configs, f)
    return path


class RobotConfigFileHandler(FileSystemEventHandler):
    callbacks: list[Callable[[FileSystemEvent, RobotConfigs], None]] = list()

    def register_observer(
        self,
        callback: Callable[[FileSystemEvent, RobotConfigs], None],
    ):
        self.callbacks.append(callback)

    @staticmethod
    def _is_target_file(event) -> bool:
        target = os.path.abspath(ROBOT_CONFIGS_PATH)
        src_path = getattr(event, "src_path", "")
        dest_path = getattr(event, "dest_path", "")
        src_match = src_path and os.path.abspath(src_path) == target
        dest_match = dest_path and os.path.abspath(dest_path) == target
        return bool(src_match or dest_match)

    def _handle_config_change(self, event: FileSystemEvent):
        from src.config.load import load_robot_config

        if not self._is_target_file(event):
            return

        try:
            logger.info("Detected change in robot config file")
            new_configs = load_robot_config()
            for callback in self.callbacks:
                callback(event, new_configs)

        except Exception as e:
            logger.error(f"Robot config file is invalid: {e}")
            path = take_backup()
            logger.info(f"Backed up existing robot configs to {path}")

    def on_modified(self, event: FileSystemEvent):
        self._handle_config_change(event)

    def on_deleted(self, event: DirDeletedEvent | FileDeletedEvent) -> None:
        if not self._is_target_file(event):
            return
        logger.warning("Robot config file deleted.")
        path = take_backup()
        logger.info(f"Backed up current robot configs to {path}")

    def on_created(self, event: DirCreatedEvent | FileCreatedEvent):
        self._handle_config_change(event)

    def on_moved(self, event: DirMovedEvent | FileMovedEvent):
        self._handle_config_change(event)


def register_listener(fh: RobotConfigFileHandler):
    """Returns a function that registers a callback to be called when the robot config file is modified or deleted.
    The callback should take in a FileSystemEvent and the new RobotConfigs as an argument."""

    def register_observer(
        callback: Callable[[FileSystemEvent, RobotConfigs], None],
    ):
        """Registers a callback to be called when the file is modified. The Callback should take the event data and parsed new config as argument.

        Args:
            callback (Callable[[FileSystemEvent, RobotConfigs], None]): _description_
        """
        fh.register_observer(callback)

    return register_observer
