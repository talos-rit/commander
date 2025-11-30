from textual.message import Message
from textual.widgets import Button


class HoldButton(Button):
    def __init__(self, *args, hold_ms=200, **kwargs):
        super().__init__(*args, **kwargs)
        self._held = False
        self._hold_timer = None
        self._hold_interval = hold_ms / 1000

    # Fires the moment the user presses
    def on_mouse_down(self, event):
        event.stop()
        self._held = True
        self.post_message(self.ButtonActive())

        # Start hold loop
        self._hold_timer = self.app.set_interval(
            self._hold_interval,
            self._on_hold,
        )

    # Fires the moment the user releases
    def on_mouse_up(self, event):
        event.stop()
        if self._held:
            self._held = False
            if self._hold_timer:
                self._hold_timer.stop()
            self.post_message(self.ButtonReleased())

    # Called repeatedly while held
    def _on_hold(self):
        if self._held:
            self.post_message(self.ButtonHold())

    # Custom Messages
    class ButtonActive(Message):
        pass

    class ButtonHold(Message):
        pass

    class ButtonReleased(Message):
        pass
