from loguru import logger
from textual import events
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import RichLog


class PrintViewer(Widget):
    """Captures print() output and displays it in a Log widget."""

    def compose(self) -> ComposeResult:
        yield RichLog(id="log")

    def on_mount(self) -> None:
        def log_handler(message) -> None:
            record = message.record
            log = self.query_one("#log", RichLog)
            # log.write(
            #     f"{record['time']} | {record['level'].name} | {record['function']} - {record['message']}"
            # )
            log.write(record["message"])

        logger.add(
            log_handler,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        )
        self.begin_capture_print()

    def on_print(self, event: events.Print) -> None:
        txt = event.text.rstrip("\n")
        if not txt:
            return
        log = self.query_one("#log", RichLog)
        log.write(txt)
        if event.stderr:
            logger.error(txt)
        else:
            logger.info(txt)
