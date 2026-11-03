from dataclasses import dataclass
from typing import Any, Literal, get_args

from src.config.schema.app import DisplayMode, OneScreenMode, UIMode

type Slot = Literal[1, 2]

DISPLAY_MODES: tuple[str, ...] = get_args(DisplayMode.__value__)
ONE_SCREEN_MODES: tuple[str, ...] = get_args(OneScreenMode.__value__)
UI_MODES: tuple[str, ...] = get_args(UIMode.__value__)


class ViewStateError(ValueError):
    """A requested view change is not possible with the current camera slots."""


@dataclass
class WebOperatorState:
    """
    What the operator is looking at and which robot their commands target.

    Every assigned camera is on screen. Camera 1 is the primary camera; Camera
    2 is optional. With one camera every command targets Camera 1. With two,
    Manual lets the operator pick the controlled camera and Dynamic leaves that
    choice to Commander.
    """

    camera_1: str | None = None
    camera_2: str | None = None
    # Saved so older configs still load. The live view ignores it.
    display_mode: DisplayMode = "one_screen"
    one_screen_mode: OneScreenMode = "manual"
    # Debug while the web UI is still in development. See AppSettings.ui_mode.
    ui_mode: UIMode = "debug"
    manual_slot: Slot = 1
    dynamic_slot: Slot = 1
    """Slot controlled in dynamic mode. Nothing moves it yet; subject-aware
    switching will call set_dynamic_slot()."""

    def __post_init__(self) -> None:
        self._reconcile()

    @classmethod
    def from_settings(cls, settings: Any) -> "WebOperatorState":
        return cls(
            camera_1=settings.camera_1_host,
            camera_2=settings.camera_2_host,
            display_mode=settings.display_mode,
            one_screen_mode=settings.one_screen_mode,
            ui_mode=settings.ui_mode,
        )

    # --- slots -----------------------------------------------------------

    @property
    def slots(self) -> dict[Slot, str]:
        slots: dict[Slot, str] = {}
        if self.camera_1:
            slots[1] = self.camera_1
        if self.camera_2:
            slots[2] = self.camera_2
        return slots

    @property
    def available_slots(self) -> int:
        return len(self.slots)

    @property
    def has_two_cameras(self) -> bool:
        return self.available_slots == 2

    def assign_slots(self, camera_1: str | None, camera_2: str | None) -> None:
        camera_1 = camera_1 or None
        camera_2 = camera_2 or None
        if camera_1 is None and camera_2 is not None:
            camera_1, camera_2 = camera_2, None
        if camera_2 == camera_1:
            camera_2 = None
        self.camera_1 = camera_1
        self.camera_2 = camera_2
        self._reconcile()

    def slot_of(self, host: str) -> Slot | None:
        return next((slot for slot, h in self.slots.items() if h == host), None)

    # --- view ------------------------------------------------------------

    @property
    def effective_display_mode(self) -> DisplayMode:
        """Feeds on screen follow how many cameras are assigned, not a layout setting."""
        return "two_screen" if self.has_two_cameras else "one_screen"

    def set_display_mode(self, mode: str) -> None:
        """Store a legacy layout value. It does not change which feeds are shown."""
        if mode not in DISPLAY_MODES:
            raise ViewStateError(f"Unknown display mode {mode!r}")
        if mode == "two_screen" and not self.has_two_cameras:
            raise ViewStateError("Two-screen mode needs a second camera assigned")
        self.display_mode = mode  # type: ignore[assignment]

    def set_one_screen_mode(self, mode: str) -> None:
        if mode not in ONE_SCREEN_MODES:
            raise ViewStateError(f"Unknown one-screen mode {mode!r}")
        self.one_screen_mode = mode  # type: ignore[assignment]

    def set_ui_mode(self, mode: str) -> None:
        if mode not in UI_MODES:
            raise ViewStateError(f"Unknown UI mode {mode!r}")
        self.ui_mode = mode  # type: ignore[assignment]

    def set_dynamic_slot(self, slot: Slot) -> None:
        if slot not in self.slots:
            raise ViewStateError(f"Camera {slot} is not assigned")
        self.dynamic_slot = slot

    @property
    def displayed_slot(self) -> Slot | None:
        """Camera that receives commands. Both feeds stay on screen either way."""
        if not self.slots:
            return None
        if not self.has_two_cameras:
            return 1
        return self.manual_slot if self.one_screen_mode == "manual" else self.dynamic_slot

    @property
    def displayed_hosts(self) -> list[str]:
        return [self.slots[slot] for slot in sorted(self.slots)]

    # --- command target --------------------------------------------------

    @property
    def selected_host(self) -> str | None:
        """Robot that receives Home, Auto-Track and jog commands.

        With one camera this is Camera 1. With two, Manual follows the
        operator and Dynamic follows dynamic_slot.
        """
        slot = self.displayed_slot
        return self.slots.get(slot) if slot is not None else None

    def select_host(self, host: str) -> None:
        slot = self.slot_of(host)
        if slot is None:
            raise ViewStateError(f"{host!r} is not assigned to a camera slot")
        self.select_slot(slot)

    def select_slot(self, slot: int) -> None:
        """Remember which camera the operator wants to control.

        Dynamic mode keeps controlling dynamic_slot. The manual choice is
        stored so it applies again when they switch back to Manual.
        """
        if slot not in self.slots:
            raise ViewStateError(f"Camera {slot} is not assigned")
        self.manual_slot = slot  # type: ignore[assignment]

    # --- helpers ---------------------------------------------------------

    def _reconcile(self) -> None:
        if self.manual_slot not in self.slots:
            self.manual_slot = 1
        if self.dynamic_slot not in self.slots:
            self.dynamic_slot = 1

    def persisted_settings(self) -> dict[str, Any]:
        return {
            "camera_1_host": self.camera_1,
            "camera_2_host": self.camera_2,
            "display_mode": self.display_mode,
            "one_screen_mode": self.one_screen_mode,
            "ui_mode": self.ui_mode,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "camera_1": self.camera_1,
            "camera_2": self.camera_2,
            "available_slots": self.available_slots,
            "display_mode": self.effective_display_mode,
            "preferred_display_mode": self.display_mode,
            "one_screen_mode": self.one_screen_mode,
            "ui_mode": self.ui_mode,
            "displayed_slot": self.displayed_slot,
            "displayed_hosts": self.displayed_hosts,
            "selected_host": self.selected_host,
        }
