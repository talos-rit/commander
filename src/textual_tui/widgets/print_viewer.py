from loguru import logger
from textual import events
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import RichLog

from src.config.load import APP_SETTINGS


class PrintViewer(Widget):
    """Captures print() output and displays it in a Log widget."""

    def compose(self) -> ComposeResult:
        yield RichLog(id="log")

    def on_mount(self) -> None:
        def log_handler(message) -> None:
            record = message.record
            try:
                log = self.query_one("#log", RichLog)
                log.write(f"[{record['level'].name}] {record['message']}")
            except Exception:
                print(record["message"])

        logger.add(
            log_handler,
            level=APP_SETTINGS.log_level,
        )
        self.begin_capture_print()

    def on_print(self, event: events.Print) -> None:
        txt = event.text.rstrip("\n")
        if not txt:
            return
        if event.stderr:
            logger.error(txt)
        else:
            logger.info(txt)
