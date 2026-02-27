import re

from loguru import logger
from textual import events
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import RichLog

from src.config.load import APP_SETTINGS

LEVEL_COLORS = {
    "DEBUG": "cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "magenta",
}


class PrintViewer(Widget):
    """Captures print() output and displays it in a Log widget."""

    def compose(self) -> ComposeResult:
        yield RichLog(id="log", highlight=True, markup=True)

    def on_mount(self) -> None:
        def log_handler(message) -> None:
            record = message.record
            try:
                color = LEVEL_COLORS.get(record["level"].name, "white")
                log = self.query_one("#log", RichLog)
                log.write(
                    f"[[{color}]{record['level'].name}[/{color}]] {record['message']}"
                )
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
        sanitized_txt = re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", txt)
        logger.info(sanitized_txt)
