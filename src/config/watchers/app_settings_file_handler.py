import os

from loguru import logger
from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileMovedEvent,
    FileSystemEventHandler,
)

from src.path_utils import get_file_path

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
    @staticmethod
    def _is_target_file(event) -> bool:
        target = os.path.abspath(APP_SETTINGS_PATH)
        src_path = getattr(event, "src_path", "")
        dest_path = getattr(event, "dest_path", "")
        src_match = src_path and os.path.abspath(src_path) == target
        dest_match = dest_path and os.path.abspath(dest_path) == target
        return bool(src_match or dest_match)

    def on_modified(self, event):
        if not self._is_target_file(event):
            return
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
        if not self._is_target_file(event):
            return
        logger.warning("App settings file deleted.")
        path = take_backup_from_app_settings()
        logger.info(f"Backed up current app settings to {path}")

    def on_created(self, event: DirCreatedEvent | FileCreatedEvent):
        self.on_modified(event)  # pyright: ignore[reportArgumentType]

    def on_moved(self, event: DirMovedEvent | FileMovedEvent):
        self.on_modified(event)  # pyright: ignore[reportArgumentType]
