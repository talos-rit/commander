from textual import events
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import RichLog


class PrintViewer(Widget):
    """Captures print() output and displays it in a Log widget."""

    def compose(self) -> ComposeResult:
        yield RichLog(id="log")

    def on_mount(self) -> None:
        self.begin_capture_print()

    def on_print(self, event: events.Print) -> None:
        log = self.query_one("#log", RichLog)
        log.write(event.text.rstrip("\n"))
