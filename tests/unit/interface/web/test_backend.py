import numpy as np
import pytest
import yaml

import src.config as config_module
from src.connection.publisher import ERVTelemetrySnapshot
from src.interface.web.backend import BackendError, CommanderWebBackend
from src.interface.web.state import WebOperatorState

from .fakes import FakeApp, robot


def make_backend(camera_1=None, camera_2=None, persisted=None, **state_kwargs):
    app = FakeApp()
    state = WebOperatorState(camera_1=camera_1, camera_2=camera_2, **state_kwargs)
    persisted = persisted if persisted is not None else []
    backend = CommanderWebBackend(
        app,
        state,
        persist_settings=persisted.append,
        model_options=lambda: ["basic", "yolo_nano"],
    )
    return backend, app, persisted


# --- single camera (the default setup) ------------------------------------


def test_startup_with_one_camera_opens_only_camera_1(web_config):
    backend, app, _ = make_backend(camera_1="a")

    backend.startup()

    assert list(app.connections) == ["a"]
    assert app.active == "a"


def test_startup_with_no_cameras_is_fine(web_config):
    backend, app, _ = make_backend()

    backend.startup()

    status = backend.status()
    assert app.connections == {}
    assert status["view"]["available_slots"] == 0
    assert status["view"]["selected_host"] is None


def test_startup_skips_slot_without_robot_config(web_config):
    backend, app, _ = make_backend(camera_1="a", camera_2="ghost")

    backend.startup()

    assert list(app.connections) == ["a"]


def test_startup_loads_saved_yolo_model(web_config, monkeypatch):
    monkeypatch.setattr(
        config_module.APP_SETTINGS, "default_model", "yolo_nano", raising=False
    )
    backend, app, _ = make_backend(camera_1="a")

    backend.startup()

    assert app.model == "yolo_nano"


def test_startup_ignores_a_saved_non_yolo_model(web_config, monkeypatch):
    monkeypatch.setattr(
        config_module.APP_SETTINGS, "default_model", "basic", raising=False
    )
    backend, app, _ = make_backend(camera_1="a")

    backend.startup()

    assert app.model == "yolo_nano"


def test_single_camera_home_and_auto_track_target_camera_1(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()

    assert backend.home() == "a"
    assert ("home", "a") in app.calls
    assert backend.set_auto_track(True) is True
    assert app.connections["a"].is_manual is False


def test_single_camera_rejects_two_screen(web_config):
    backend, _, persisted = make_backend(camera_1="a")
    backend.startup()

    with pytest.raises(BackendError) as err:
        backend.set_view(display_mode="two_screen")

    assert err.value.status == 409
    assert backend.status()["view"]["display_mode"] == "one_screen"
    assert persisted == []


def test_commands_without_any_camera_explain_what_to_do(web_config):
    backend, _, _ = make_backend()

    with pytest.raises(BackendError, match="Settings"):
        backend.home()


# --- two cameras ------------------------------------------------------------


def test_home_and_auto_track_hit_selected_host_in_two_screen(web_config):
    backend, app, _ = make_backend(camera_1="a", camera_2="b")
    backend.startup()
    backend.set_view(display_mode="two_screen")

    backend.select(host="b")
    backend.home()
    backend.set_auto_track(True)

    assert app.active == "b"
    assert ("home", "b") in app.calls
    assert app.connections["b"].is_manual is False
    assert app.connections["a"].is_manual is True


def test_home_disables_auto_tracking_first(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()
    backend.set_auto_track(True)

    backend.home()

    manual_index = app.calls.index(("manual", True, "a"))
    assert manual_index < app.calls.index(("home", "a"))
    assert app.connections["a"].is_manual is True


def test_explicit_host_overrides_selection(web_config):
    backend, app, _ = make_backend(camera_1="a", camera_2="b")
    backend.startup()

    backend.home(host="b")

    assert ("home", "b") in app.calls


def test_select_slot_keeps_both_feeds_and_switches_the_active_camera(web_config):
    backend, app, _ = make_backend(camera_1="a", camera_2="b")
    backend.startup()

    backend.select(slot=2)

    view = backend.status()["view"]
    assert view["displayed_hosts"] == ["a", "b"]
    assert view["selected_host"] == "b"
    assert app.active == "b"


def test_select_requires_host_or_slot(web_config):
    backend, _, _ = make_backend(camera_1="a")
    with pytest.raises(BackendError):
        backend.select()


def test_independent_tracking_survives_selection_and_manual_handoff(web_config):
    class Control:
        def __init__(self):
            self.enabled = False

        def set_enabled(self, enabled):
            self.enabled = enabled
            return enabled

        def manual_handoff(self):
            pass

        def status(self):
            return {"robot_fault": None}

    backend, _, _ = make_backend(camera_1="a", camera_2="b", ui_mode="debug")
    backend.startup()
    controls = {host: Control() for host in ("a", "b")}
    backend._pi_vision.update(controls)
    assert backend.set_auto_track(True, host="a")
    # Explicitly addressed tracking can arm the other robot too.
    assert backend.set_auto_track(True, host="b")
    backend.select(host="b")
    assert all(control.enabled for control in controls.values())
    backend.move("left", True)
    assert controls["a"].enabled
    assert not controls["b"].enabled


def test_select_unassigned_slot_is_conflict(web_config):
    backend, _, _ = make_backend(camera_1="a")
    with pytest.raises(BackendError) as err:
        backend.select(slot=2)
    assert err.value.status == 409


def test_set_view_persists_preferences(web_config):
    backend, _, persisted = make_backend(camera_1="a", camera_2="b")
    backend.startup()

    backend.set_view(display_mode="two_screen", one_screen_mode="dynamic")

    assert persisted[-1]["display_mode"] == "two_screen"
    assert persisted[-1]["one_screen_mode"] == "dynamic"


def test_assign_slots_opens_new_and_closes_removed_connections(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()

    backend.assign_slots("b", None)

    assert list(app.connections) == ["b"]
    assert ("disconnect", "a") in app.calls
    assert app.active == "b"


def test_assign_slots_adds_optional_second_camera(web_config):
    backend, app, persisted = make_backend(camera_1="a")
    backend.startup()

    backend.assign_slots("a", "b")

    assert set(app.connections) == {"a", "b"}
    assert app.active == "a"  # opening b must not steal the selection
    assert persisted[-1]["camera_2_host"] == "b"


def test_assign_unknown_robot_is_not_found(web_config):
    backend, _, _ = make_backend(camera_1="a")
    with pytest.raises(BackendError) as err:
        backend.assign_slots("a", "ghost")
    assert err.value.status == 404


# --- auto-track details -------------------------------------------------------


def test_auto_track_loads_a_model_when_none_selected(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()

    backend.set_auto_track(True)

    assert app.model == "yolo_nano"


def test_auto_track_explains_when_yolo_is_not_installed(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend._model_options = lambda: ["basic", "mediapipe"]
    backend.startup()

    with pytest.raises(BackendError) as err:
        backend.set_auto_track(True)

    assert err.value.status == 500
    assert "uv sync --extra yolo" in str(err.value)
    assert app.model is None


def test_auto_track_reports_model_failure(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()
    app.change_model_result = False

    with pytest.raises(BackendError) as err:
        backend.set_auto_track(True)
    assert err.value.status == 500


def test_auto_track_refused_for_manual_only_robot(web_config):
    web_config.robots["a"] = robot("a", manual_only=True)
    backend, _, _ = make_backend(camera_1="a")
    backend.startup()

    with pytest.raises(BackendError) as err:
        backend.set_auto_track(True)
    assert err.value.status == 409


def test_auto_track_off(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()
    backend.set_auto_track(True)

    assert backend.set_auto_track(False) is False
    assert app.connections["a"].is_manual is True


def test_virtual_camera_streams_the_selected_robot(web_config):
    backend, app, _ = make_backend(camera_1="a", camera_2="b")
    backend.startup()
    backend.select(slot=2)

    assert backend.set_virtual_camera(True) is True

    assert ("start_stream", "pyvcam", None) in app.calls
    assert app.active == "b"
    assert backend.status()["virtual_camera"] is True

    assert backend.set_virtual_camera(False) is False
    assert app.calls[-1] == ("stop_stream",)
    assert backend.status()["virtual_camera"] is False


def test_virtual_camera_requires_a_frame(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()
    app.connections["a"].video_connection.shape = None

    with pytest.raises(BackendError) as err:
        backend.set_virtual_camera(True)

    assert err.value.status == 409
    assert not any(call[0] == "start_stream" for call in app.calls)


def test_virtual_camera_reports_a_missing_device(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()
    app.stream_error = RuntimeError("obs backend: virtual camera is not installed")

    with pytest.raises(BackendError) as err:
        backend.set_virtual_camera(True)

    assert err.value.status == 500
    assert "Virtual Camera" in str(err.value)
    assert backend.status()["virtual_camera"] is False


# --- debug controls -----------------------------------------------------------


def test_jog_requires_debug_mode(web_config):
    backend, _, _ = make_backend(camera_1="a", ui_mode="simple")
    backend.startup()

    with pytest.raises(BackendError) as err:
        backend.move("up", active=True)
    assert err.value.status == 403


def test_jog_in_debug_mode_targets_selected_robot(web_config):
    backend, app, _ = make_backend(camera_1="a", camera_2="b", ui_mode="debug")
    backend.startup()
    backend.select(slot=2)

    backend.move("left", active=True)
    backend.move("left", active=False)

    assert ("continuous_move", "LEFT", "b") in app.calls
    assert ("stop_continuous_move", "LEFT", "b") in app.calls


def test_left_and_right_pan_follow_the_button(web_config):
    backend, app, _ = make_backend(camera_1="a", ui_mode="debug")
    backend.startup()

    backend.move("left", active=True)
    backend.move("right", active=True)
    backend.move("up", active=True)
    backend.move("down", active=True)

    assert [call[1] for call in app.calls if call[0] == "continuous_move"] == [
        "LEFT",
        "RIGHT",
        "UP",
        "DOWN",
    ]


def test_fault_blocks_new_jogs_but_allows_stop_and_explicit_clear(web_config):
    from types import SimpleNamespace
    backend, app, _ = make_backend(camera_1="a", ui_mode="debug")
    backend.startup()
    control = SimpleNamespace(
        status=lambda: {"robot_fault": "IMPACT PROTECTION AXIS 2"},
        set_enabled=lambda enabled: False,
    )
    backend._pi_vision["a"] = control
    for action in (
        lambda: backend.move("left", True),
        lambda: backend.joint_jog("shoulder", 1, True),
        lambda: backend.cartesian(1, 0, 0, True),
    ):
        with pytest.raises(BackendError, match="IMPACT") as error:
            action()
        assert error.value.status == 409
    backend.joint_jog("shoulder", 1, False)
    app.calls.clear()
    backend.clear_robot_error()
    assert ("stop_all", "a") in app.calls
    assert app.connections["a"].publisher.calls == [("enable",)]
    assert not any(call[0] == "start_joint" for call in app.calls)


def test_joint_and_cartesian_jog_target_the_selected_robot(web_config):
    backend, app, _ = make_backend(camera_1="a", camera_2="b", ui_mode="debug")
    backend.startup()
    backend.select(slot=2)

    backend.joint_jog("elbow", -1, active=True)
    backend.joint_jog("elbow", -1, active=False)
    backend.cartesian(0, -1, 0, active=True)
    backend.cartesian(0, 0, 0, active=False)

    assert ("start_joint", 3, -1, "b") in app.calls
    assert ("stop_joint", "b") in app.calls
    assert ("start_cartesian", (0, -1, 0), "b") in app.calls
    assert ("stop_cartesian", "b") in app.calls


def test_speed_enable_and_stop_match_the_operator_panel(web_config):
    backend, app, _ = make_backend(camera_1="a", ui_mode="debug")
    backend.startup()

    assert backend.status()["speed_percent"] is None
    assert backend.set_speed_percent(40) == 40
    assert app.connections["a"].publisher.calls == [("speed", 40)]
    assert backend.status()["speed_percent"] == 40

    backend.enable_control()
    assert ("enable",) in app.connections["a"].publisher.calls

    backend.move("up", active=True)
    backend.stop_motion()
    assert ("stop_all", "a") in app.calls

    with pytest.raises(BackendError) as err:
        backend.set_speed_percent(0)
    assert err.value.status == 422
    assert backend.status()["speed_percent"] == 40


def test_speed_and_enable_require_debug_mode(web_config):
    backend, _, _ = make_backend(camera_1="a", ui_mode="simple")
    backend.startup()
    with pytest.raises(BackendError) as err:
        backend.set_speed_percent(20)
    assert err.value.status == 403
    with pytest.raises(BackendError) as blocked:
        backend.enable_control()
    assert blocked.value.status == 403


def test_joint_jog_rejects_unknown_axis(web_config):
    backend, _, _ = make_backend(camera_1="a", ui_mode="debug")
    backend.startup()
    with pytest.raises(BackendError):
        backend.joint_jog("wrist", 1, active=True)


def test_arm_jog_requires_debug_mode(web_config):
    backend, _, _ = make_backend(camera_1="a", ui_mode="simple")
    backend.startup()
    with pytest.raises(BackendError) as err:
        backend.joint_jog("shoulder", 1, active=True)
    assert err.value.status == 403


def test_jog_unknown_direction(web_config):
    backend, _, _ = make_backend(camera_1="a", ui_mode="debug")
    backend.startup()
    with pytest.raises(BackendError):
        backend.move("sideways", active=True)


def test_leaving_debug_mode_stops_jogging(web_config):
    backend, app, _ = make_backend(camera_1="a", ui_mode="debug")
    backend.startup()

    backend.set_view(ui_mode="simple")

    assert ("stop_all", "a") in app.calls


def test_set_jog_mode_applies_and_persists(web_config):
    backend, app, persisted = make_backend(camera_1="a")
    backend.startup()

    backend.set_jog_mode("continuous")

    assert str(app.control_mode) == "continuous"
    assert {"jog_mode": "continuous"} in persisted
    with pytest.raises(BackendError):
        backend.set_jog_mode("warp")


def test_set_model_validates_option(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()

    assert backend.set_model("yolo_nano") == "yolo_nano"
    assert backend.set_model(None) is None
    with pytest.raises(BackendError) as err:
        backend.set_model("nope")
    assert err.value.status == 404
    app.change_model_result = False
    with pytest.raises(BackendError) as failed:
        backend.set_model("yolo_nano")
    assert failed.value.status == 409
    with pytest.raises(BackendError) as rejected:
        backend.set_model("basic")
    assert rejected.value.status == 404


# --- status / video -------------------------------------------------------------


def test_status_reports_twin_telemetry(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()
    app.connections["a"].publisher.telemetry = ERVTelemetrySnapshot(
        encoder_counts=tuple(range(11)),
        encoder_received_monotonic=None,
        joint_counts=(1, 2, 3, 4, 5),
        joint_received_monotonic=None,
    )

    status = backend.status()

    host = status["connections"]["a"]
    assert host["operator_connected"] is True
    assert host["has_video"] is True
    assert host["slot"] == 1
    assert host["telemetry"]["joint_counts"] == [1, 2, 3, 4, 5]
    assert host["telemetry"]["encoder_counts"] == list(range(11))
    assert host["telemetry"]["joint_age_s"] is None
    assert status["tracking"]["input_fps"] == 12.3
    assert status["tracking"]["model_options"] == ["yolo_nano"]
    assert status["tracking"]["default_model"] == "yolo_nano"
    assert status["robots"] == ["a", "b"]
    app.connections["a"].publisher.get_command_receipt = lambda: {
        "sent": 1, "acked": 1, "last_command": "Home", "last_sent_age_s": 0.1, "last_ack_age_s": 0.05, "last_failed": False,
    }
    assert backend.status()["connections"]["a"]["command"]["last_command"] == "Home"


def test_status_for_unopened_slot(web_config):
    backend, app, _ = make_backend(camera_1="a")

    host = backend.status()["connections"]["a"]

    assert host["open"] is False
    assert host["operator_connected"] is False
    assert host["telemetry"] is None


def test_status_telemetry_absent_for_publishers_without_it(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()
    app.connections["a"].publisher = object()

    host = backend.status()["connections"]["a"]
    assert host["telemetry"] is None
    assert host["operator_connected"] is False


def test_get_frame_and_sequence(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()

    assert isinstance(backend.get_frame("a"), np.ndarray)
    assert backend.frame_sequence("a") == 0
    assert backend.get_frame("zzz") is None
    assert backend.frame_sequence("zzz") is None
    assert backend.frame_fps("a") == 30
    assert backend.frame_fps("zzz") == 30


# --- settings / robots ----------------------------------------------------------


def test_update_settings_persists_to_yaml_and_memory(web_config):
    app = FakeApp()
    backend = CommanderWebBackend(
        app, WebOperatorState(camera_1="a"), model_options=lambda: ["basic"]
    )
    backend.startup()

    result = backend.update_settings({"camera_2_host": "b", "default_model": "basic"})

    assert result["camera_2_host"] == "b"
    assert config_module.APP_SETTINGS.default_model == "basic"
    saved = yaml.safe_load(web_config.app_settings_path.read_text())
    assert saved["camera_2_host"] == "b"
    assert saved["default_model"] == "basic"
    assert set(app.connections) == {"a", "b"}


def test_update_settings_two_screen_default_without_second_camera(web_config):
    backend, _, persisted = make_backend(camera_1="a")
    backend.startup()

    backend.update_settings({"display_mode": "two_screen"})

    assert backend.state.display_mode == "two_screen"
    assert backend.status()["view"]["display_mode"] == "one_screen"


def test_update_settings_rejects_invalid_values_without_side_effects(web_config):
    backend, app, persisted = make_backend(camera_1="a")
    backend.startup()

    with pytest.raises(BackendError) as err:
        backend.update_settings({"camera_2_host": "b", "ui_mode": "wizard"})

    assert err.value.status == 422
    assert "b" not in app.connections
    assert persisted == []


def test_add_robot_persists_and_fills_empty_camera_1(web_config):
    web_config.robots.clear()
    backend, app, persisted = make_backend()

    created = backend.add_robot(
        {"socket_host": "bluey", "socket_port": "61616", "camera_index": "rtsp://x"}
    )

    assert created["socket_port"] == 61616
    assert "bluey" in config_module.ROBOT_CONFIGS
    assert backend.state.camera_1 == "bluey"
    assert backend.state.camera_2 is None
    assert any(item.get("camera_1_host") == "bluey" for item in persisted)
    assert "bluey" in app.connections
    saved = yaml.safe_load(web_config.robot_configs_path.read_text())
    assert saved["bluey"]["camera_index"] == "rtsp://x"


def test_add_robot_leaves_feed_2_empty(web_config):
    backend, _, _ = make_backend(camera_1="a")

    backend.add_robot({"socket_host": "c", "socket_port": "61616", "camera_index": "0"})

    assert backend.state.camera_1 == "a"
    assert backend.state.camera_2 is None


def test_disabled_pi_vision_keeps_the_url_without_starting_it(web_config):
    web_config.robots["a"] = robot(
        "a", pi_vision_enabled=False, pi_vision_url="http://pi:5050"
    )
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()

    assert "a" in app.connections
    assert "a" not in backend._pi_vision
    assert config_module.ROBOT_CONFIGS["a"].pi_vision_url == "http://pi:5050"


def test_add_robot_validation_errors(web_config):
    backend, _, _ = make_backend(camera_1="a")
    with pytest.raises(BackendError) as err:
        backend.add_robot({"socket_host": "a", "socket_port": "1", "camera_index": "0"})
    assert err.value.status == 422
    assert "already exists" in str(err.value)


def test_update_robot_reopens_connection(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()

    updated = backend.update_robot("a", {"camera_index": "rtsp://new", "fps": 15})

    assert updated["camera_index"] == "rtsp://new"
    assert config_module.ROBOT_CONFIGS["a"].fps == 15
    assert app.calls.count(("open", "a")) == 2
    assert ("disconnect", "a") in app.calls


def test_update_robot_errors(web_config):
    backend, _, _ = make_backend(camera_1="a")
    with pytest.raises(BackendError) as err:
        backend.update_robot("ghost", {})
    assert err.value.status == 404
    with pytest.raises(BackendError) as err:
        backend.update_robot("a", {"socket_port": 0})
    assert err.value.status == 422


def test_delete_robot_in_slot_promotes_remaining_camera(web_config):
    backend, app, _ = make_backend(camera_1="a", camera_2="b")
    backend.startup()

    backend.delete_robot("a")

    assert backend.state.camera_1 == "b"
    assert backend.state.camera_2 is None
    assert "a" not in config_module.ROBOT_CONFIGS
    assert "a" not in app.connections


def test_delete_unknown_robot(web_config):
    backend, _, _ = make_backend()
    with pytest.raises(BackendError) as err:
        backend.delete_robot("ghost")
    assert err.value.status == 404


def test_list_robots(web_config):
    backend, _, _ = make_backend()
    assert list(backend.list_robots()) == ["a", "b"]


# --- zoom -----------------------------------------------------------------------


def _person(track_id, box, confidence=0.9):
    from src.observations.types import PersonObservation

    return PersonObservation("a", 0, 0.0, box, confidence, track_id)


def test_status_lists_subjects_sorted_by_subject_id(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()
    app.connections["a"].set_observations(
        [_person(7, (1, 2, 3, 4), 0.81234), _person(2, (500, 6, 507, 8))]
    )
    app.connections["a"].set_observations(
        [_person(2, (500, 6, 507, 8)), _person(7, (1, 2, 3, 4), 0.81234)]
    )

    host = backend.status()["connections"]["a"]

    assert [s["id"] for s in host["subject_list"]] == [1, 2]
    assert host["subject_list"][0] == {"id": 1, "confidence": 0.812, "box": [1, 2, 3, 4]}
    assert host["zoom"]["target"] is None
    assert host["zoom"]["fill"] == pytest.approx(0.6)


def test_zoom_target_sets_focus_on_selected_robot(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()
    app.connections["a"].set_observations([_person(3, (1, 2, 3, 4))])

    assert backend.set_zoom_target(1) == 1
    assert app.connections["a"].focus_subject_id == 1
    assert backend.status()["connections"]["a"]["zoom"]["target"] == 1

    assert backend.set_zoom_target(None) is None
    assert app.connections["a"].focus_subject_id is None


def test_zoom_target_may_be_out_of_view_but_must_be_known(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()
    app.connections["a"].set_observations([_person(3, (1, 2, 3, 4))])
    app.connections["a"].set_observations([])

    assert backend.set_zoom_target(1) == 1
    with pytest.raises(BackendError) as err:
        backend.set_zoom_target(9)

    assert err.value.status == 404
    assert app.connections["a"].focus_subject_id == 1


def test_zoom_fill_is_validated(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()

    assert backend.set_zoom_fill(0.8) == pytest.approx(0.8)
    assert app.streamer.zoom("a").fill == pytest.approx(0.8)
    with pytest.raises(BackendError) as err:
        backend.set_zoom_fill(1.5)
    assert err.value.status == 422


# --- recognition ----------------------------------------------------------------


def test_status_reports_recognition_and_the_targets_last_match(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()
    app.connections["a"].set_observations([_person(3, (1, 2, 3, 4))])
    backend.set_zoom_target(1)

    status = backend.status()

    assert status["recognition"] == {"known": 1, "appearance": False, "faces": False, "leniency": 0.5}
    assert status["connections"]["a"]["zoom"]["match"] is None
    app.identity._subjects[1].match = ("face", 0.912)
    assert backend.status()["connections"]["a"]["zoom"]["match"] == {"by": "face", "score": 0.91}


def test_saved_leniency_is_applied_at_startup(web_config):
    import src.config as config_module

    config_module.APP_SETTINGS.recognition_leniency = 0.8  # web_config isolates APP_SETTINGS
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()

    assert app.identity.leniency == 0.8


def test_set_recognition_leniency_applies_validates_and_persists(web_config):
    backend, app, persisted = make_backend(camera_1="a")
    backend.startup()

    assert backend.set_recognition_leniency(0.25) == 0.25

    assert app.identity.leniency == 0.25
    assert app.identity.match_threshold == pytest.approx(0.9)
    assert {"recognition_leniency": 0.25} in persisted
    with pytest.raises(BackendError) as err:
        backend.set_recognition_leniency(1.5)
    assert err.value.status == 422


def test_forget_subjects_clears_everyone_and_zooms_out(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()
    app.connections["a"].set_observations([_person(3, (1, 2, 3, 4))])
    backend.set_zoom_target(1)

    assert backend.forget_subjects()["known"] == 0

    assert app.connections["a"].focus_subject_id is None
    with pytest.raises(BackendError):
        backend.set_zoom_target(1)


def test_recognition_controls_are_debug_only(web_config):
    backend, _, _ = make_backend(camera_1="a", ui_mode="simple")
    backend.startup()

    for call in (lambda: backend.set_recognition_leniency(0.5), backend.forget_subjects):
        with pytest.raises(BackendError) as err:
            call()
        assert err.value.status == 403


def test_leniency_saved_through_settings_applies_now(web_config):
    backend, app, persisted = make_backend(camera_1="a")
    backend.startup()

    backend.update_settings({"recognition_leniency": 0.9})

    assert app.identity.leniency == 0.9
    assert any(update.get("recognition_leniency") == 0.9 for update in persisted)
    with pytest.raises(BackendError):
        backend.update_settings({"recognition_leniency": 3})


def test_web_twin_reuses_measured_calibration(web_config):
    from src.simulation.erv_calibration import BASE_CALIBRATION, map_arm_controller_coordinates
    import time
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()
    publisher = app.connections["a"].publisher
    publisher.telemetry = ERVTelemetrySnapshot(None, None, (100, 1500, 2200, 1200, 99), time.monotonic())
    pose = backend.status()["connections"]["a"]["telemetry"]["joint_positions"]
    assert pose == {**map_arm_controller_coordinates(1500, 2200, 1200), "base_joint": BASE_CALIBRATION.to_urdf(100)}
    assert "roll_joint" not in pose
    publisher.telemetry = ERVTelemetrySnapshot(None, None, (1500, 2200, 1200, 99), time.monotonic())
    pose = backend.status()["connections"]["a"]["telemetry"]["joint_positions"]
    assert "base_joint" not in pose
    publisher.telemetry = ERVTelemetrySnapshot(tuple(range(11)), time.monotonic(), None, None)
    assert backend.status()["connections"]["a"]["telemetry"]["joint_positions"] is None


def test_controller_profile_mismatch_blocks_motion_but_allows_stop(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()
    backend.set_view(ui_mode="debug")
    app.connections["a"].publisher.get_controller_profile = lambda: "esp-one-axis"
    assert backend.status()["connections"]["a"]["controller"]["state"] == "mismatch"
    for action in (lambda: backend.home(), lambda: backend.move("right", True), lambda: backend.set_auto_track(True)):
        with pytest.raises(BackendError) as error:
            action()
        assert error.value.status == 409
    backend.stop_motion()


def test_esp_profile_restricts_controls_and_native_can_be_restored(web_config):
    import src.config as config
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()
    backend.set_view(ui_mode="debug")
    config.ROBOT_CONFIGS["a"].controller_profile = "esp-one-axis"
    app.connections["a"].publisher.get_controller_profile = lambda: "esp-one-axis"
    backend.move("right", True)
    backend.move("right", False)
    for action in (lambda: backend.move("up", True), lambda: backend.joint_jog("elbow", 1, True), lambda: backend.cartesian(0, 1, 0, True), lambda: backend.enable_control(), lambda: backend.set_speed_percent(20), lambda: backend.clear_robot_error()):
        with pytest.raises(BackendError) as error:
            action()
        assert error.value.status == 409
    config.ROBOT_CONFIGS["a"].controller_profile = "native"
    assert backend.status()["connections"]["a"]["controller"]["state"] == "mismatch"
    app.connections["a"].publisher.get_controller_profile = lambda: "native"
    backend.move("up", True)
    backend.enable_control()


def test_unknown_controller_profile_blocks_home(web_config):
    backend, app, _ = make_backend(camera_1="a")
    backend.startup()
    app.connections["a"].publisher.get_controller_profile = lambda: None
    with pytest.raises(BackendError):
        backend.home()


def test_two_named_robots_can_share_a_pi_with_separate_ports(web_config):
    import src.config as config
    backend, app, _ = make_backend()
    backend.add_robot({"robot_id": "bluey", "socket_host": "shared.local", "socket_port": 61616, "camera_index": "rtsp://shared.local:8554/camera", "controller_profile": "esp-one-axis"})
    backend.add_robot({"robot_id": "bingo", "socket_host": "shared.local", "socket_port": 61617, "camera_index": "rtsp://shared.local:8554/bingo", "controller_profile": "native"})
    assert config.ROBOT_CONFIGS["bluey"].socket_host == config.ROBOT_CONFIGS["bingo"].socket_host == "shared.local"
    assert config.ROBOT_CONFIGS["bluey"].socket_port == 61616
    assert config.ROBOT_CONFIGS["bingo"].socket_port == 61617
    backend.update_robot("bluey", {"socket_host": "replacement.local"})
    assert config.ROBOT_CONFIGS["bluey"].socket_host == "replacement.local"
    assert config.ROBOT_CONFIGS["bingo"].socket_host == "shared.local"
