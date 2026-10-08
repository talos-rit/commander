from types import SimpleNamespace

import pytest

from src.interface.web.state import ViewStateError, WebOperatorState


def test_empty_state_has_no_target_or_feeds():
    state = WebOperatorState()

    assert state.available_slots == 0
    assert state.selected_host is None
    assert state.displayed_hosts == []
    assert state.displayed_slot is None


def test_single_camera_is_one_screen_and_targets_camera_1():
    state = WebOperatorState(camera_1="bluey")

    assert state.available_slots == 1
    assert state.has_two_cameras is False
    assert state.effective_display_mode == "one_screen"
    assert state.displayed_hosts == ["bluey"]
    assert state.selected_host == "bluey"


def test_single_camera_rejects_two_screen():
    state = WebOperatorState(camera_1="bluey")

    with pytest.raises(ViewStateError):
        state.set_display_mode("two_screen")
    assert state.effective_display_mode == "one_screen"
    assert state.displayed_hosts == ["bluey"]


def test_saved_two_screen_preference_waits_for_second_camera():
    state = WebOperatorState(camera_1="bluey", display_mode="two_screen")

    assert state.effective_display_mode == "one_screen"
    state.assign_slots("bluey", "bingo")
    assert state.effective_display_mode == "two_screen"
    assert state.displayed_hosts == ["bluey", "bingo"]


def test_single_camera_cannot_select_camera_2():
    state = WebOperatorState(camera_1="bluey")

    with pytest.raises(ViewStateError):
        state.select_slot(2)


def test_two_screen_keeps_both_feeds_and_selection_follows_clicked_pane():
    state = WebOperatorState(camera_1="a", camera_2="b")
    state.set_display_mode("two_screen")

    assert state.displayed_hosts == ["a", "b"]
    assert state.selected_host == "a"
    state.select_host("b")
    assert state.selected_host == "b"
    assert state.displayed_hosts == ["a", "b"]


def test_one_screen_manual_shows_chosen_camera_until_changed():
    state = WebOperatorState(camera_1="a", camera_2="b", one_screen_mode="manual")

    state.select_slot(2)
    assert state.displayed_hosts == ["b"]
    assert state.selected_host == "b"
    state.set_one_screen_mode("manual")
    assert state.displayed_hosts == ["b"]


def test_one_screen_dynamic_stub_does_not_switch_on_its_own():
    state = WebOperatorState(camera_1="a", camera_2="b")
    state.set_one_screen_mode("dynamic")

    assert state.displayed_hosts == ["a"]
    state.select_slot(2)  # manual choice does not drive dynamic mode
    assert state.displayed_hosts == ["a"]
    state.set_dynamic_slot(2)
    assert state.displayed_hosts == ["b"]
    assert state.selected_host == "b"


def test_selecting_host_in_one_screen_switches_the_manual_feed():
    state = WebOperatorState(camera_1="a", camera_2="b")

    state.select_host("b")
    assert state.displayed_hosts == ["b"]


def test_select_unknown_host_raises():
    with pytest.raises(ViewStateError):
        WebOperatorState(camera_1="a").select_host("nope")


def test_assign_slots_promotes_camera_2_and_drops_duplicates():
    state = WebOperatorState()

    state.assign_slots(None, "b")
    assert (state.camera_1, state.camera_2) == ("b", None)
    state.assign_slots("a", "a")
    assert (state.camera_1, state.camera_2) == ("a", None)
    state.assign_slots("", "")
    assert state.slots == {}


def test_removing_camera_2_resets_selection_and_view():
    state = WebOperatorState(camera_1="a", camera_2="b")
    state.set_display_mode("two_screen")
    state.select_host("b")

    state.assign_slots("a", None)

    assert state.effective_display_mode == "one_screen"
    assert state.selected_host == "a"
    assert state.manual_slot == 1


@pytest.mark.parametrize(
    "setter,value",
    [("set_display_mode", "three"), ("set_one_screen_mode", "auto"), ("set_ui_mode", "pro")],
)
def test_invalid_mode_values_raise(setter, value):
    with pytest.raises(ViewStateError):
        getattr(WebOperatorState(camera_1="a"), setter)(value)


def test_set_dynamic_slot_requires_assigned_slot():
    with pytest.raises(ViewStateError):
        WebOperatorState(camera_1="a").set_dynamic_slot(2)


def test_from_settings_and_serialization():
    settings = SimpleNamespace(
        camera_1_host="a",
        camera_2_host=None,
        display_mode="two_screen",
        one_screen_mode="dynamic",
        ui_mode="debug",
    )
    state = WebOperatorState.from_settings(settings)

    data = state.to_dict()
    assert data["available_slots"] == 1
    assert data["display_mode"] == "one_screen"
    assert data["preferred_display_mode"] == "two_screen"
    assert data["selected_host"] == "a"
    assert data["ui_mode"] == "debug"
    assert state.persisted_settings() == {
        "camera_1_host": "a",
        "camera_2_host": None,
        "display_mode": "two_screen",
        "one_screen_mode": "dynamic",
        "ui_mode": "debug",
    }
