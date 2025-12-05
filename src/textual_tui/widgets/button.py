from rich.text import TextType
from textual.message import Message
from textual.widgets import Button
from typing_extensions import Literal

ButtonVariant = Literal["default", "primary", "success", "warning", "error"]


class ReactiveButton(Button):
    def __init__(
        self,
        label: TextType | None = None,
        seconds_to_disable_on_mount: int | None = 1,
        on_blur=None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = True,
    ):
        super().__init__(
            label=label,
            name=name,
            id=id,
            classes=classes,
            disabled=disabled,
        )
        self.on_btn_blur = on_blur

        def enable():
            self.disabled = False

        self.set_timer(
            seconds_to_disable_on_mount or 0,
            enable,
        )

    class Active(Message):
        def __init__(self, button):
            self.button: ReactiveButton = button
            super().__init__()

        @property
        def control(self):
            return self.button

    class Released(Message):
        def __init__(self, button):
            self.button: ReactiveButton = button
            super().__init__()

        @property
        def control(self):
            return self.button

    def on_focus(self):
        self.post_message(ReactiveButton.Active(self))

    def on_click(self):
        self.post_message(ReactiveButton.Released(self))
        if self.on_btn_blur:
            self.on_btn_blur()
        else:
            # Not preferred as it will put focus on another random component.
            self.blur()
