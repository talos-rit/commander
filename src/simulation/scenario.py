"""Small deterministic scenario runner using normal Publisher methods."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Mapping

from src.robot_state import RobotStateSnapshot, RobotStateSource

from .publisher import SimulatedPublisher
from .robot import RobotPose


class ScenarioAction(str, Enum):
    HOME = "home"
    POLAR_CONTINUOUS = "polar_continuous"
    POLAR_DISCRETE = "polar_discrete"
    MOVE_TO = "move_to"
    SET_SPEED = "set_speed"
    STOP = "stop"


@dataclass(frozen=True, order=True)
class ScenarioEvent:
    at: float
    action: ScenarioAction = field(compare=False)
    arguments: Mapping[str, int | float] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if self.at < 0:
            raise ValueError("scenario event time must be non-negative")


@dataclass(frozen=True)
class Scenario:
    events: tuple[ScenarioEvent, ...]
    duration: float

    def __post_init__(self) -> None:
        if self.duration < 0:
            raise ValueError("scenario duration must be non-negative")
        if any(event.at > self.duration for event in self.events):
            raise ValueError("scenario event occurs after its duration")


class ScenarioRunner:
    """Advances the deterministic plant; visualization remains an observer."""

    def __init__(
        self,
        publisher: SimulatedPublisher,
        state_source: RobotStateSource,
        timestep: float = 1 / 60,
    ) -> None:
        if timestep <= 0:
            raise ValueError("timestep must be positive")
        self.publisher = publisher
        self.state_source = state_source
        self.timestep = timestep

    def run(
        self,
        scenario: Scenario,
        on_snapshot: Callable[[RobotStateSnapshot], None] | None = None,
        *,
        realtime: bool = False,
    ) -> tuple[RobotStateSnapshot, ...]:
        events = sorted(scenario.events)
        start_time = self.publisher.get_state().timestamps.updated_at
        index = 0
        elapsed = 0.0
        snapshots: list[RobotStateSnapshot] = []

        def emit() -> None:
            snapshot = self.state_source.get_snapshot()
            snapshots.append(snapshot)
            if on_snapshot:
                on_snapshot(snapshot)

        emit()
        while elapsed < scenario.duration:
            while index < len(events) and events[index].at <= elapsed + 1e-12:
                self._dispatch(events[index])
                index += 1
                emit()
            step = min(self.timestep, scenario.duration - elapsed)
            next_event = events[index].at if index < len(events) else None
            if next_event is not None and elapsed < next_event < elapsed + step:
                step = next_event - elapsed
            before = time.perf_counter()
            self.publisher.advance(step)
            elapsed = self.publisher.get_state().timestamps.updated_at - start_time
            emit()
            if realtime:
                remaining = step - (time.perf_counter() - before)
                if remaining > 0:
                    time.sleep(remaining)

        while index < len(events) and events[index].at <= elapsed + 1e-12:
            self._dispatch(events[index])
            index += 1
            emit()
        return tuple(snapshots)

    def _dispatch(self, event: ScenarioEvent) -> None:
        values = event.arguments
        if event.action == ScenarioAction.HOME:
            self.publisher.home(values.get("delay_ms", 0))
        elif event.action == ScenarioAction.POLAR_CONTINUOUS:
            self.publisher.polar_pan_continuous_start(
                values.get("azimuth", 0), values.get("altitude", 0)
            )
        elif event.action == ScenarioAction.POLAR_DISCRETE:
            self.publisher.polar_pan_discrete(
                values.get("azimuth", 0),
                values.get("altitude", 0),
                values.get("delay_ms", 0),
                values.get("duration_ms", 0),
            )
        elif event.action == ScenarioAction.SET_SPEED:
            self.publisher.set_speed(int(values["speed"]))
        elif event.action == ScenarioAction.STOP:
            self.publisher.polar_pan_continuous_stop()
        elif event.action == ScenarioAction.MOVE_TO:
            self.publisher.move_to(
                RobotPose(
                    azimuth=float(values.get("azimuth", 0)),
                    altitude=float(values.get("altitude", 0)),
                    x=float(values.get("x", 0)),
                    y=float(values.get("y", 0)),
                    z=float(values.get("z", 0)),
                ),
                duration=(
                    float(values["duration"])
                    if "duration" in values
                    else None
                ),
            )
        else:  # pragma: no cover - Enum prevents this through the public API
            raise ValueError(f"unsupported scenario action: {event.action}")


def demo_scenario() -> Scenario:
    """Exercise latency, continuous/discrete movement, preemption, and settling."""

    return Scenario(
        events=(
            ScenarioEvent(0.0, ScenarioAction.HOME),
            ScenarioEvent(
                2.0,
                ScenarioAction.POLAR_CONTINUOUS,
                {"azimuth": -1, "altitude": 0},
            ),
            ScenarioEvent(3.5, ScenarioAction.SET_SPEED, {"speed": 110}),
            ScenarioEvent(
                4.0,
                ScenarioAction.POLAR_CONTINUOUS,
                {"azimuth": 1, "altitude": 0},
            ),
            ScenarioEvent(4.5, ScenarioAction.STOP),
            ScenarioEvent(
                5.0,
                ScenarioAction.MOVE_TO,
                {"azimuth": 25, "altitude": 10, "duration": 1.8},
            ),
        ),
        duration=8.0,
    )
