import os

from loguru import logger
from watchdog.events import DirDeletedEvent, FileDeletedEvent, FileSystemEventHandler

from ...utils import get_file_path
from ..path import APP_SETTINGS_PATH, BACKUP_DIR
from ..schema.app import AppSettings


def take_backup_from_app_settings() -> str:
    import src.config as config

    app_settings = config.APP_SETTINGS.model_dump()
    path = get_file_path(os.path.join(BACKUP_DIR, APP_SETTINGS_PATH + ".backup"))
    if os.path.exists(path):
        ind = 1
        while os.path.exists(path + str(ind)):
            ind += 1
        path += str(ind)
    with open(path, "w") as f:
        import yaml

        yaml.safe_dump(app_settings, f)
    return path


class AppSettingFileHandler(FileSystemEventHandler):
    def on_modified(self, event):
        try:
            logger.info("Detected change in app settings file, verifying changes...")
            AppSettings()
            logger.info(
                "App settings file is valid. Please restart the application to apply changes."
            )
        except Exception as e:
            logger.error(f"App settings file is invalid: {e}")
            path = take_backup_from_app_settings()
            logger.info(f"Backed up existing app settings to {path}")

    def on_deleted(self, event: DirDeletedEvent | FileDeletedEvent) -> None:
        logger.warning("App settings file deleted.")
        path = take_backup_from_app_settings()
        logger.info(f"Backed up current app settings to {path}")
