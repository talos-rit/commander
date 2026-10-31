import threading

import pytest

from src.burn_in import (
    MAX_SPEED_PERCENT,
    BurnInConfig,
    Move,
    PoseCounts,
    RealArm,
    TwinArm,
    base_command_degrees,
    config_from_args,
    controller_shift_counts,
    cycle,
    fault_kind,
    fault_text,
    plan_step,
    run_burn_in,
)
from src.burn_in import _build_parser
from src.simulation.robot import CommandKind


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.stop = None

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds
        if self.stop is not None and self.now >= 0.2:
            self.stop.set()


def _config(**overrides) -> BurnInConfig:
    values = dict(duration_s=3 * 60 * 60, interval_s=4.0, move_limit=16)
    values.update(overrides)
    return BurnInConfig(**values)


class ScriptedArm:
    def __init__(self) -> None:
        self.counts = PoseCounts(0, 1000, 2000, 1100)
        self.age = 0.0
        self.fault = None
        self.commands: list[Move] = []
        self.enables = 0
        self.speed = None
        self.shift_on_prepare = 0
        self.ignore_motion = False
        self.motion_scale = 1.0
        self.fault_on_command = None
        self.repeat_fault = False
        self._origin = self.counts

    def prepare(self) -> PoseCounts:
        self._origin = self.counts
        if self.shift_on_prepare:
            self.counts = PoseCounts(
                self.counts.base + self.shift_on_prepare,
                self.counts.shoulder,
                self.counts.elbow,
                self.counts.pitch,
            )
        return self._origin

    def peek_fault(self):
        return self.fault

    def pop_fault(self):
        fault = self.fault
        if not self.repeat_fault:
            self.fault = None
        return fault

    def latest(self):
        return self.counts, self.age

    def set_speed_percent(self, percent: int) -> None:
        self.speed = percent

    def enable_control(self) -> None:
        self.enables += 1
        if not self.repeat_fault:
            self.fault = None

    def command(self, move: Move) -> bool:
        self.commands.append(move)
        if self.fault_on_command:
            self.fault = self.fault_on_command
            if not self.repeat_fault:
                self.fault_on_command = None
            return True
        if self.ignore_motion:
            return True
        self.counts = PoseCounts(
            self.counts.base + int(round(controller_shift_counts(move.base_degrees) * self.motion_scale)),
            self.counts.shoulder + int(round(move.shoulder * self.motion_scale)),
            self.counts.elbow + int(round(move.elbow * self.motion_scale)),
            self.counts.pitch + int(round(move.pitch * self.motion_scale)),
        )
        return True

    def close(self) -> None:
        return None


def test_base_step_matches_the_controller_cast():
    assert controller_shift_counts(2) == int(2 * 42.5666)
    assert base_command_degrees(controller_shift_counts(2), 2) == 2
    assert base_command_degrees(20, 2) == 0
    assert base_command_degrees(50, 2) == 1
    assert base_command_degrees(-controller_shift_counts(2), 2) == -2


def test_plan_moves_one_axis_toward_the_start_pose():
    config = _config()
    origin = PoseCounts(0, 1000, 2000, 1100)
    outward = plan_step(origin, origin, "shoulder", 1, config)
    assert outward == Move("shoulder", shoulder=40)
    back = plan_step(origin, PoseCounts(0, 1040, 2000, 1100), "shoulder", 0, config)
    assert back.shoulder == -40
    assert back.base_degrees == 0
    assert back.elbow == 0
    assert back.pitch == 0


def test_config_rejects_moves_large_enough_to_sweep_the_workspace():
    with pytest.raises(ValueError):
        BurnInConfig(speed_percent=MAX_SPEED_PERCENT + 1)
    with pytest.raises(ValueError):
        BurnInConfig(azimuth_step_deg=30)
    with pytest.raises(ValueError):
        BurnInConfig(interval_s=0.5)
    with pytest.raises(ValueError):
        BurnInConfig(shoulder_step_counts=500)
    with pytest.raises(ValueError):
        BurnInConfig(duration_s=9 * 60 * 60)


def test_default_cli_stays_on_the_twin():
    args = _build_parser().parse_args([])
    assert args.real is False
    config = config_from_args(args)
    assert config.speed_percent <= MAX_SPEED_PERCENT
    assert config.azimuth_step_deg <= 5


def test_fault_lines_ignore_telemetry():
    assert fault_text("TELP 1 2 3 4 5") is None
    assert fault_text("FAULT CONTROL DISABLED") == "FAULT CONTROL DISABLED"
    assert fault_kind("IMPACT protection") == "impact"
    assert fault_kind("ACL - unrecognized request") == "protocol"
    assert fault_kind("CONTROL DISABLED") == "recoverable"


def test_cycle_returns_to_the_start_pose():
    arm = ScriptedArm()
    result = run_burn_in(arm, _config(), clock=FakeClock())

    assert result.code == 0
    assert result.commands == 16
    assert [move.axis for move in arm.commands] == [axis for axis, _sign in cycle(_config())]
    for move in arm.commands:
        assert abs(move.base_degrees) <= 2
        assert abs(move.shoulder) <= 40
        assert abs(move.elbow) <= 40
        assert abs(move.pitch) <= 12
        assert bool(move.base_degrees) != bool(move.shoulder or move.elbow or move.pitch)
    assert arm.counts == arm._origin
    assert arm.speed == 15


def test_recoverable_fault_is_cleared_and_the_soak_continues():
    arm = ScriptedArm()
    arm.fault_on_command = "FAULT CONTROL DISABLED"
    result = run_burn_in(arm, _config(move_limit=4), clock=FakeClock())

    assert result.code == 0
    assert result.faults_cleared == 1
    assert arm.enables == 1
    assert result.commands == 4


def test_impact_is_cleared_once_and_the_soak_stops():
    arm = ScriptedArm()
    arm.fault_on_command = "IMPACT"
    result = run_burn_in(arm, _config(), clock=FakeClock())

    assert result.code == 5
    assert arm.enables == 1
    assert result.commands == 1


def test_a_fault_that_will_not_clear_stops_without_more_motion():
    arm = ScriptedArm()
    arm.fault_on_command = "CONTROL DISABLED"
    arm.repeat_fault = True
    result = run_burn_in(arm, _config(), clock=FakeClock())

    assert result.code == 2
    assert arm.enables == 3
    assert result.commands == 1


def test_envelope_breach_sends_no_move():
    arm = ScriptedArm()
    arm.shift_on_prepare = 10_000
    result = run_burn_in(arm, _config(), clock=FakeClock())

    assert result.code == 4
    assert arm.commands == []
    assert arm.enables == 0


def test_arm_that_does_not_move_stops():
    arm = ScriptedArm()
    arm.ignore_motion = True
    result = run_burn_in(arm, _config(), clock=FakeClock())

    assert result.code == 6
    assert result.commands == 3


def test_runaway_stops_inside_the_wider_envelope():
    arm = ScriptedArm()
    arm.motion_scale = 2.4
    result = run_burn_in(arm, _config(), clock=FakeClock())

    assert result.code == 7
    assert result.commands == 1


def test_stop_during_a_dwell_sends_nothing_further():
    stop = threading.Event()
    clock = FakeClock()
    clock.stop = stop
    arm = ScriptedArm()

    result = run_burn_in(arm, _config(), stop=stop, clock=clock)

    assert result.code == 130
    assert result.commands == 1


def test_twin_clears_a_fault_through_the_simulated_robot():
    arm = TwinArm()
    arm.fail_next("CONTROL DISABLED")
    result = run_burn_in(arm, _config(move_limit=2), clock=FakeClock())

    assert result.code == 0
    assert arm.enable_calls == 1
    assert arm.robot.get_state().fault is None
    assert all(command.kind != CommandKind.HOME for command in arm.robot.command_history)
    assert arm.robot.get_state().pose.azimuth == pytest.approx(2)
    arm.close()


def test_real_arm_clears_a_startup_fault_with_con_and_refuses_an_impact():
    class Publisher:
        def __init__(self) -> None:
            self.calls = []
            self.failed = False
            self.counts = (10, 1088, 2113, 1151, 0)
            self.listeners = []
            self.operator_connection = self

        def add_message_listener(self, listener) -> None:
            self.listeners.append(listener)

        def is_connected(self) -> bool:
            return True

        def handshake(self) -> None:
            self.calls.append("handshake")

        def get_erv_joint_counts(self):
            return self.counts

        def get_erv_telemetry_received_monotonic(self):
            return 0.0

        def erv_enable_control(self) -> None:
            self.calls.append("con")

        def erv_set_speed_percent(self, percent: int) -> None:
            self.calls.append(("speed", percent))

        def get_command_receipt(self):
            return {"last_failed": self.failed, "sent": 1}

        def close(self) -> None:
            self.calls.append("close")

    publisher = Publisher()
    arm = RealArm(publisher, clock=FakeClock())
    publisher.listeners[0]("FAULT IMPACT on the base")

    result = run_burn_in(arm, _config(), clock=FakeClock())

    assert result.code == 1
    assert "con" in publisher.calls
    assert ("speed", 15) in publisher.calls
    arm.close()
