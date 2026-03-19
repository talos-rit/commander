import sys

from src.utils import (
    add_termination_handler,
    calculate_acceptable_box,
    calculate_center_box,
    calculate_center_bbox,
    get_file_path,
    id_generator,
    remove_termination_handler,
    start_termination_guard,
    terminate,
)


def test_get_file_path_returns_relative_when_not_frozen(monkeypatch):
    monkeypatch.delenv("_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    assert get_file_path("some/path.txt") == "some/path.txt"


def test_get_file_path_uses_meipass_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert get_file_path("some/path.txt") == str(tmp_path / "some/path.txt")


def test_calculate_center_box_and_bbox():
    assert calculate_center_box(0, 0, 10, 10) == (5, 5)
    assert calculate_center_bbox((0, 0, 10, 10)) == (5, 5)

def test_calculate_acceptable_box_default_percent(monkeypatch):
    # Using a predictable default percent from DEFAULT_ROBOT_CONFIG (likely 0.5)
    # The function should compute a centered square.
    box = calculate_acceptable_box(100, 200, acceptable_box_percent=0.5)
    assert box == (25, 50, 75, 150)


def test_id_generator_increments():
    gen = id_generator()
    assert next(gen) == 0
    assert next(gen) == 1
    assert next(gen) == 2


def test_termination_handlers_lifecycle(monkeypatch):
    # Ensure signal.signal doesn't actually register during tests
    monkeypatch.setattr("signal.signal", lambda *args, **kwargs: None)

    called = []

    def handler():
        called.append(True)

    start_termination_guard()
    handler_id = add_termination_handler(handler)
    assert handler_id is not None

    terminate(signum=0, frame=None)
    assert called == [True]

    # After terminate, handlers list should be empty and removal should be safe
    remove_termination_handler(handler_id)
