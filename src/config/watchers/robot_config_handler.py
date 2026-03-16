import os

from loguru import logger
from watchdog.events import DirDeletedEvent, FileDeletedEvent, FileSystemEventHandler

from ...utils import get_file_path
from ..path import BACKUP_DIR, ROBOT_CONFIGS_PATH


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
    def on_modified(self, event):
        try:
            logger.info("Detected change in robot config file")

        except Exception as e:
            logger.error(f"Robot config file is invalid: {e}")
            path = take_backup()
            logger.info(f"Backed up existing robot configs to {path}")

    def on_deleted(self, event: DirDeletedEvent | FileDeletedEvent) -> None:
        logger.warning("Robot config file deleted.")
        path = take_backup()
        logger.info(f"Backed up current robot configs to {path}")
