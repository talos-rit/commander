from loguru import logger
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from ..utils import add_termination_handler
from .read import APP_SETTINGS_PATH
from .schema.app import AppSettings


class AppSettingsEventHandler(FileSystemEventHandler):
    def on_any_event(self, event: FileSystemEvent) -> None:
        print(event)


class AppSettingsManager:
    _observer = None

    @staticmethod
    def edit_app_settings(on_change=None, on_error=None) -> None:
        """
        Edit the app settings and save to file.
        Args:
            new_settings: A validated AppSettings object with the new settings to save.
        """
        import src.config as config

        try:
            app_settings = AppSettings()
            logger.info(
                f"Current App Settings: {app_settings.model_dump_json(indent=2)}"
            )
            if on_change is not None:
                on_change(app_settings)
            config.APP_SETTINGS = app_settings
        except Exception as e:
            logger.error("Error loading app settings, using defaults\n" + str(e))
            if on_error is not None:
                on_error(e)

    @staticmethod
    def start_watch_dog():
        if AppSettingsManager._observer is not None:
            logger.warning("Watchdog already running, skipping start")
            return
        event_handler = AppSettingsEventHandler()
        observer = Observer()
        AppSettingsManager._observer = observer
        observer.schedule(event_handler, APP_SETTINGS_PATH)
        observer.start()
        logger.info("Started watchdog to monitor app settings changes")
        add_termination_handler(AppSettingsManager.stop_watch_dog)

    @staticmethod
    def stop_watch_dog():
        if AppSettingsManager._observer is not None:
            AppSettingsManager._observer.stop()
            AppSettingsManager._observer = None
            logger.info("Stopped watchdog monitoring app settings changes")
