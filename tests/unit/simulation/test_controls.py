import time

import pytest

from src.simulation.control_panel import (
    CARTESIAN_HOLD_DIRECTIONS,
    POLAR_HOLD_DIRECTIONS,
    TkSimulationControlPanel,
)
from src.simulation import (
    AxisLimits,
    InteractiveSimulationController,
    KeyboardFlags,
    RobotLimits,
    RobotPose,
    SimulationConfig,
    SimulatedPublisher,
    SimulatedRobot,
    SimulatedRobotStateSource,
)
from src.simulation.erv_calibration import (
    BASE_CALIBRATION,
    map_arm_controller_coordinates,
)


class FakeViewer:
    def __init__(self) -> None:
        self.snapshots = []
        self.steps = []

    def get_keyboard_events(self):
        return {}

    def update(self, snapshot) -> None:
        self.snapshots.append(snapshot)

    def step(self, seconds=None) -> None:
        self.steps.append(seconds)

    def is_connected(self) -> bool:
        return False


class RecordingRealPublisher:
    def __init__(self) -> None:
        self.calls = []
        self.connected = True
        self.telemetry_received = None
        self.joint_counts = None

    def _record(self, name, *args):
        self.calls.append((name, args))

    def home(self, delay):
        self._record("home", delay)

    def polar_pan_continuous_start(self, azimuth, altitude):
        self._record("polar_start", azimuth, altitude)

    def polar_pan_continuous_stop(self):
        self._record("polar_stop")

    def cartesian_move_continuous_start(self, x, y, z):
        self._record("cartesian_start", x, y, z)

    def cartesian_move_continuous_stop(self):
        self._record("cartesian_stop")

    def polar_pan_discrete(self, azimuth, altitude, delay, duration):
        self._record("polar_discrete", azimuth, altitude, delay, duration)

    def cartesian_move_discrete(self, x, y, z, delay, duration):
        self._record("cartesian_discrete", x, y, z, delay, duration)

    def set_speed(self, speed):
        self._record("set_speed", speed)

    def erv_joint_jog_start(self, axis, direction):
        self._record("joint_jog_start", axis, direction)

    def erv_joint_jog_stop(self):
        self._record("joint_jog_stop")

    def get_erv_encoder_counts(self):
        return self.encoder_counts

    def get_erv_joint_counts(self):
        return self.joint_counts

    def get_erv_telemetry_received_monotonic(self):
        return self.telemetry_received

    def emit_telemetry(self, counts, joint_counts=None):
        self.encoder_counts = counts
        self.joint_counts = joint_counts
        self.telemetry_received = time.monotonic()

    def is_connected(self):
        return self.connected


class FakeClock:
    def __init__(self): self.value = 0.0
    def __call__(self): return self.value
    def advance(self, seconds): self.value += seconds


class BoundButton:
    def __init__(self) -> None:
        self.handlers = {}

    def bind(self, event, callback) -> None:
        self.handlers[event] = callback


class FocusRoot:
    def __init__(self, focused) -> None:
        self.focused = focused

    def after_idle(self, callback) -> None:
        callback()

    def focus_displayof(self):
        return self.focused


class FocusedWidget:
    def __init__(self, toplevel) -> None:
        self._toplevel = toplevel

    def winfo_toplevel(self):
        return self._toplevel


def make_controller():
    robots = {
        robot_id: SimulatedRobot(SimulationConfig(command_latency=0))
        for robot_id in ("bluey", "erv")
    }
    publishers = {
        robot_id: SimulatedPublisher(robot) for robot_id, robot in robots.items()
    }
    sources = {
        robot_id: SimulatedRobotStateSource(robot_id, robot)
        for robot_id, robot in robots.items()
    }
    viewer = FakeViewer()
    controller = InteractiveSimulationController(
        publishers,
        sources,
        viewer,
        KeyboardFlags(is_down=1, was_triggered=2),
        timestep=0.1,
    )
    return controller, robots, viewer


def make_limited_controller():
    limits = RobotLimits(azimuth=AxisLimits(-1.0, 1.0))
    robot = SimulatedRobot(
        SimulationConfig(
            command_latency=0,
            settling_time=0,
            limits=limits,
            speed=RobotPose(azimuth=10.0),
        )
    )
    publisher = SimulatedPublisher(robot)
    viewer = FakeViewer()
    controller = InteractiveSimulationController(
        {"bluey": publisher},
        {"bluey": SimulatedRobotStateSource("bluey", robot)},
        viewer,
        KeyboardFlags(is_down=1, was_triggered=2),
        timestep=0.2,
    )
    return controller, robot


def test_keyboard_commands_selected_robot_through_simulated_publisher() -> None:
    controller, robots, viewer = make_controller()

    controller.process_keyboard({ord("d"): 1 | 2})
    snapshots = controller.advance_once()

    assert robots["bluey"].get_state().pose.azimuth == 3.0
    assert robots["erv"].get_state().pose.azimuth == 0.0
    assert {snapshot.robot_id for snapshot in snapshots} == {"bluey", "erv"}
    assert len(viewer.snapshots) == 2


def test_tab_changes_robot_and_home_returns_state() -> None:
    controller, robots, _viewer = make_controller()
    controller.process_keyboard({ord("\t"): 2})
    controller.process_keyboard({ord("h"): 2})

    snapshots = controller.advance_once()

    assert controller.selected_robot_id == "erv"
    erv = next(state for state in snapshots if state.robot_id == "erv")
    assert erv.current_command is None
    assert erv.homed is True
    assert robots["bluey"].get_state().homed is False


def test_releasing_continuous_key_sends_stop() -> None:
    controller, robots, _viewer = make_controller()
    controller.process_keyboard({ord("w"): 1})
    controller.advance_once()
    extended_y = robots["bluey"].get_state().pose.y

    controller.process_keyboard({})
    controller.advance_once()

    assert extended_y < 0
    assert robots["bluey"].get_state().movement_state.value == "idle"


def test_j_and_k_tilt_head_without_rotating_base() -> None:
    controller, robots, _viewer = make_controller()

    controller.process_keyboard({ord("j"): 2})
    command = robots["bluey"].get_state().current_command

    assert command is not None
    assert command.target is not None
    assert command.target.azimuth == 0
    assert command.target.altitude == 10


def test_cartesian_controls_update_returned_mock_state_without_fake_joints() -> None:
    controller, _robots, _viewer = make_controller()

    controller.move_cartesian_discrete(0, 100, 100)
    for _ in range(10):
        snapshots = controller.advance_once()

    bluey = next(state for state in snapshots if state.robot_id == "bluey")
    assert bluey.logical_pose is not None
    assert bluey.logical_pose.y == pytest.approx(100)
    assert bluey.logical_pose.z == pytest.approx(100)
    assert bluey.joint_positions is None


def test_press_and_release_cartesian_control_starts_and_stops_motion() -> None:
    controller, robots, _viewer = make_controller()

    controller.start_cartesian_continuous(0, 1, 0)
    controller.advance_once()
    moving_y = robots["bluey"].get_state().pose.y
    controller.stop_continuous()
    controller.advance_once()

    assert moving_y > 0
    assert robots["bluey"].get_state().pose.y == moving_y
    assert robots["bluey"].get_state().movement_state.value == "idle"


def test_empty_keyboard_poll_does_not_cancel_mouse_held_movement() -> None:
    controller, robots, _viewer = make_controller()

    controller.start_polar_continuous(1, 0)
    for _ in range(5):
        controller.process_keyboard({})
        controller.advance_once()

    assert robots["bluey"].get_state().pose.azimuth == pytest.approx(15.0)
    assert robots["bluey"].get_state().movement_state.value == "moving"

    controller.stop_continuous()
    controller.advance_once()
    assert robots["bluey"].get_state().movement_state.value == "idle"


def test_hold_button_stops_once_on_leave_then_release() -> None:
    button = BoundButton()
    calls = []
    TkSimulationControlPanel._bind_hold_button(
        button, lambda: calls.append("start"), lambda: calls.append("stop")
    )

    button.handlers["<ButtonPress-1>"](None)
    button.handlers["<Leave>"](None)
    button.handlers["<ButtonRelease-1>"](None)

    assert calls == ["start", "stop"]


def test_hold_button_does_not_stop_from_its_own_focus_transition() -> None:
    button = BoundButton()
    TkSimulationControlPanel._bind_hold_button(button, lambda: None, lambda: None)

    assert "<FocusOut>" not in button.handlers


def test_window_focus_loss_stops_jog_but_child_focus_does_not() -> None:
    panel = object.__new__(TkSimulationControlPanel)
    calls = []
    panel.controller = type("Controller", (), {"stop_joint_jog": lambda self: calls.append("stop")})()
    panel.root = FocusRoot(None)

    panel._stop_jog_if_window_loses_focus(None)
    assert calls == ["stop"]

    calls.clear()
    panel.root = FocusRoot(None)
    panel.root.focused = FocusedWidget(panel.root)
    panel._stop_jog_if_window_loses_focus(None)
    assert calls == []


def test_real_backend_routes_commands_without_a_fake_pose() -> None:
    controller, robots, viewer = make_controller()
    real = RecordingRealPublisher()
    real.encoder_counts = None
    controller.real_publishers["bluey"] = real

    controller.set_selected_backend("real")
    controller.start_cartesian_continuous(0, 1, 0)
    snapshots = controller.advance_once()

    assert ("cartesian_start", (0, 1, 0)) in real.calls
    assert robots["bluey"].get_state().pose.y == 0
    bluey = next(snapshot for snapshot in snapshots if snapshot.robot_id == "bluey")
    assert bluey.source_type.value == "real"
    assert bluey.movement_state == "unknown"
    assert bluey.logical_pose is None
    assert viewer.snapshots[-2].robot_id == "bluey"


def test_real_joint_coordinate_frames_drive_joint_positions() -> None:
    controller, _robots, _viewer = make_controller()
    real = RecordingRealPublisher()
    real.emit_telemetry((10, 100, 200, 300), (10, 100, 200, 300, 400))
    controller.real_publishers["bluey"] = real
    controller.set_selected_backend("real")

    controller.advance_once()
    real.emit_telemetry((43, 16484, -16184, 1136), (43, 16484, -16184, 1136, 0))
    snapshots = controller.advance_once()

    bluey = next(snapshot for snapshot in snapshots if snapshot.robot_id == "bluey")
    assert bluey.source_type.value == "real"
    assert bluey.logical_pose is None
    expected = map_arm_controller_coordinates(16484, -16184, 1136)
    expected["base_joint"] = BASE_CALIBRATION.to_urdf(43)
    assert bluey.joint_positions == pytest.approx(expected)


def test_real_backend_is_unavailable_until_registered() -> None:
    controller, _robots, _viewer = make_controller()

    assert controller.available_backends() == ("virtual",)
    with pytest.raises(ValueError, match="unavailable"):
        controller.set_selected_backend("real")


def test_real_backend_cannot_clear_a_simulation_fault() -> None:
    controller, robots, _viewer = make_controller()
    controller.real_publishers["bluey"] = RecordingRealPublisher()
    controller.set_selected_backend("real")
    controller.clear_selected_simulation_fault()

    assert robots["bluey"].get_state().fault is None


def test_joint_jog_only_routes_to_real_publisher_without_simulated_pose_change() -> None:
    controller, robots, _viewer = make_controller()
    real = RecordingRealPublisher()
    controller.real_publishers["bluey"] = real

    assert controller.start_joint_jog(2, 1) is False
    controller.set_selected_backend("real")
    before = robots["bluey"].get_state().pose

    assert controller.start_joint_jog(2, 1) is True
    assert controller.stop_joint_jog() is True

    assert ("joint_jog_start", (2, 1)) in real.calls
    assert ("joint_jog_stop", ()) in real.calls
    assert robots["bluey"].get_state().pose == before


def test_selecting_another_robot_stops_the_old_real_joint_jog() -> None:
    controller, _robots, _viewer = make_controller()
    bluey_real = RecordingRealPublisher()
    controller.real_publishers["bluey"] = bluey_real
    controller.set_selected_backend("real")

    assert controller.start_joint_jog(3, -1) is True
    controller.select_robot("erv")

    assert controller.selected_robot_id == "erv"
    assert bluey_real.calls == [
        ("joint_jog_start", (3, -1)),
        ("joint_jog_stop", ()),
    ]


def test_joint_jog_heartbeat_refreshes_while_held_and_stops_on_release():
    controller, _robots, _viewer = make_controller()
    real, clock = RecordingRealPublisher(), FakeClock()
    controller.real_publishers["bluey"] = real
    controller._clock = clock
    controller.set_selected_backend("real")

    assert controller.start_joint_jog(2, 1)
    clock.advance(controller.manual_jog_refresh_seconds - 0.01)
    assert not controller.service_joint_jog_heartbeat()
    clock.advance(0.02)
    assert controller.service_joint_jog_heartbeat()
    assert real.calls == [("joint_jog_start", (2, 1)), ("joint_jog_start", (2, 1))]
    assert controller.manual_jog_refresh_seconds < controller.manual_jog_timeout_seconds

    assert controller.stop_joint_jog()
    clock.advance(10)
    assert not controller.service_joint_jog_heartbeat()
    assert real.calls[-1] == ("joint_jog_stop", ())


def test_real_polar_hold_heartbeats_and_stops_on_release():
    controller, _robots, _viewer = make_controller()
    real, clock = RecordingRealPublisher(), FakeClock()
    controller.real_publishers["bluey"] = real
    controller._clock = clock
    controller.set_selected_backend("real")

    assert controller.start_polar_continuous(1, 0) is not None
    clock.advance(controller.manual_jog_refresh_seconds - 0.01)
    assert not controller.service_real_polar_heartbeat()
    clock.advance(0.02)
    assert controller.service_real_polar_heartbeat()
    assert real.calls == [("polar_start", (1, 0)), ("polar_start", (1, 0))]

    controller.stop_continuous()
    clock.advance(10)
    assert not controller.service_real_polar_heartbeat()
    assert real.calls[-1] == ("polar_stop", ())


def test_real_polar_stops_refreshing_when_connection_is_lost():
    controller, _robots, _viewer = make_controller()
    real, clock = RecordingRealPublisher(), FakeClock()
    controller.real_publishers["bluey"] = real
    controller._clock = clock
    controller.set_selected_backend("real")
    controller.start_polar_continuous(0, -1)

    real.connected = False
    clock.advance(1)
    assert not controller.service_real_polar_heartbeat()
    assert real.calls == [("polar_start", (0, -1))]


def test_joint_jog_stops_refreshing_when_connection_or_backend_is_lost():
    controller, _robots, _viewer = make_controller()
    real, clock = RecordingRealPublisher(), FakeClock()
    controller.real_publishers["bluey"] = real
    controller._clock = clock
    controller.set_selected_backend("real")
    controller.start_joint_jog(3, -1)
    real.connected = False
    clock.advance(1)
    assert not controller.service_joint_jog_heartbeat()
    assert real.calls == [("joint_jog_start", (3, -1))]

    # A virtual backend never owns a held real jog or sends refresh traffic.
    controller._backend_modes["bluey"] = "virtual"
    assert not controller.service_joint_jog_heartbeat()


def test_backend_switch_cancels_active_jog_immediately():
    controller, _robots, _viewer = make_controller()
    real = RecordingRealPublisher()
    controller.real_publishers["bluey"] = real
    controller.set_selected_backend("real")
    controller.start_joint_jog(2, -1)
    controller.set_selected_backend("virtual")
    assert real.calls[-1] == ("joint_jog_stop", ())


def test_panel_hold_directions_are_normalized_for_continuous_commands() -> None:
    polar_directions = [
        row[index + 1]
        for row in POLAR_HOLD_DIRECTIONS
        for index in range(0, len(row), 2)
        if row[index + 1] is not None
    ]
    cartesian_directions = [values for _label, values in CARTESIAN_HOLD_DIRECTIONS]

    assert all(value in (-1, 0, 1) for move in polar_directions for value in move)
    assert all(
        value in (-1, 0, 1) for move in cartesian_directions for value in move
    )


def test_panel_polar_labels_describe_the_observed_hardware_axes() -> None:
    labeled_directions = {
        row[index]: row[index + 1]
        for row in POLAR_HOLD_DIRECTIONS
        for index in range(0, len(row), 2)
        if row[index]
    }

    assert labeled_directions == {
        "Base rotate +": (0, 1),
        "Base rotate -": (0, -1),
        "Claw rotate +": (1, 0),
        "Claw rotate -": (-1, 0),
    }


def test_limit_fault_is_reported_without_callback_exception_and_can_be_cleared() -> None:
    controller, robot = make_limited_controller()

    controller.start_polar_continuous(1, 0)
    controller.advance_once()
    assert robot.get_state().fault is not None

    assert controller.start_polar_continuous(-1, 0) is None
    assert "cannot move while the robot is faulted" in controller.last_error["bluey"]

    controller.clear_selected_simulation_fault()
    assert robot.get_state().fault is None
    assert controller.start_polar_continuous(-1, 0) is not None
    controller.advance_once()
    assert robot.get_state().pose.azimuth < 1.0


def test_real_hold_still_stops_when_visual_estimate_is_faulted() -> None:
    controller, robot = make_limited_controller()
    real = RecordingRealPublisher()
    controller.real_publishers["bluey"] = real

    controller.start_polar_continuous(1, 0)
    controller.advance_once()
    assert robot.get_state().fault is not None
    controller.set_selected_backend("real")

    assert controller.start_cartesian_continuous(0, 1, 0) is not None
    assert "command estimate unavailable" in controller.last_error["bluey"]
    controller.stop_continuous()

    assert ("cartesian_start", (0, 1, 0)) in real.calls
    assert ("cartesian_stop", ()) in real.calls
