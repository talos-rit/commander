import os

from loguru import logger
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from ..utils import add_termination_handler, remove_termination_handler


class DebugFileSystemEventHandler(FileSystemEventHandler):
    def on_any_event(self, event: FileSystemEvent):
        logger.debug(f"File event detected: {event.event_type} on {event.src_path}")


class FileManager:
    _observers: dict[str, BaseObserver] = dict()
    _term = None

    @staticmethod
    def _resolve_watch_path(path_value: str) -> str:
        """Watch directories for both file and directory inputs."""
        normalized = os.path.abspath(path_value)
        if os.path.isdir(normalized):
            return normalized
        return os.path.dirname(normalized) or "."

    @staticmethod
    def register_listener(
        file_path: str,
        listener: FileSystemEventHandler,
        recursive: bool = False,
        event_filter: list[type[FileSystemEvent]] | None = None,
    ):
        """
        Registers a listener function that will be called when the file change is detected.
        Args:
            listener: A function that takes a FileSystemEvent as an argument. The event will contain information about the type of change (created, modified, deleted, moved), the src_path (the path of the file that triggered the event), and dest_path (the destination path for moved events, or None for other events).
        """
        if FileManager._term is None:
            FileManager._term = add_termination_handler(FileManager.terminate)
        watch_path = FileManager._resolve_watch_path(file_path)
        if watch_path not in FileManager._observers:
            FileManager.start_watch_dog(watch_path)
        FileManager._observers[watch_path].schedule(
            listener, watch_path, recursive=recursive, event_filter=event_filter
        )
        logger.debug(
            f"Registered listener for file: {file_path} (watching {watch_path})"
        )

    @staticmethod
    def start_watch_dog(
        file_path: str, debug: bool = True
    ):  # TODO: hook debug to env var
        if file_path not in FileManager._observers:
            FileManager._observers[file_path] = Observer()
            FileManager._observers[file_path].start()
            logger.debug(f"Started watchdog for file: {file_path} {debug=}")
        if debug:
            FileManager._observers[file_path].schedule(
                DebugFileSystemEventHandler(), file_path, recursive=False
            )

    @staticmethod
    def stop_watch_dog(file_path: str):
        if file_path not in FileManager._observers:
            return
        obs = FileManager._observers.pop(file_path)
        obs.stop()
        logger.debug(f"Stopped watchdog for file: {file_path}")
        if FileManager._term is not None and not FileManager._observers:
            remove_termination_handler(FileManager._term)
            FileManager._term = None

    @staticmethod
    def terminate():
        if FileManager._term is not None:
            remove_termination_handler(FileManager._term)
        for file_path, obs in FileManager._observers.items():
            obs.stop()
            logger.debug(f"Stopped watchdog for file: {file_path}")
        FileManager._observers.clear()
        if FileManager._term is not None:
            remove_termination_handler(FileManager._term)
            FileManager._term = None
