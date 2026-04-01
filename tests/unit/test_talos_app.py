import pytest

import src.talos_app as talos_app


@pytest.fixture(autouse=True)
def patch_talos_app_dependencies(monkeypatch, mocker):
    """Patch heavy dependencies so App initialization is lightweight."""

    # Prevent Tracker/Streamer/Director side effects
    mock_tracker = mocker.Mock()
    mock_streamer = mocker.Mock()
    mock_director = mocker.Mock()

    monkeypatch.setattr(talos_app, "Tracker", lambda connections, scheduler, smm: mock_tracker)
    monkeypatch.setattr(talos_app, "Streamer", lambda connections, draw_bboxes: mock_streamer)
    monkeypatch.setattr(
        talos_app, "ContinuousDirector", lambda tracker, connections, scheduler: mock_director
    )

    # Prevent SharedMemoryManager from spawning subprocesses
    monkeypatch.setattr(talos_app, "SharedMemoryManager", lambda: mocker.Mock(spec=talos_app.SharedMemoryManager))

    # Prevent default scheduler from spawning threads
    monkeypatch.setattr(talos_app, "ThreadScheduler", lambda: mocker.Mock(spec=talos_app.ThreadScheduler))

    # Prevent global termination handler state from leaking between tests
    import src.connection.connection as connection_module

    monkeypatch.setattr(connection_module, "add_termination_handler", lambda f: 1)
    monkeypatch.setattr(connection_module, "remove_termination_handler", lambda term: None)

    yield {
        "tracker": mock_tracker,
        "streamer": mock_streamer,
        "director": mock_director,
    }


@pytest.fixture
def app_under_test(patch_talos_app_dependencies, mocker):
    scheduler = mocker.Mock()
    smm = mocker.Mock()
    app = talos_app.App(scheduler=scheduler, smm=smm)
    return app


def test_app_init_sets_up_components(app_under_test, patch_talos_app_dependencies):
    app = app_under_test

    assert app.scheduler is not None
    assert app.connections is not None
    assert app.tracker is patch_talos_app_dependencies["tracker"]
    assert app.streamer is patch_talos_app_dependencies["streamer"]
    assert app.director is patch_talos_app_dependencies["director"]


def test_open_connection_skips_existing(monkeypatch, app_under_test, mocker):
    app = app_under_test

    # Ensure 'hostname' already exists in the connection collection
    conn = mocker.Mock()
    app.connections["host"] = conn

    mock_warning = mocker.Mock()
    monkeypatch.setattr(talos_app.logger, "warning", mock_warning)

    app.open_connection("host")
    mock_warning.assert_called_once()
    assert "already exists" in mock_warning.call_args.args[0]


def test_open_connection_missing_config_logs_error(monkeypatch, app_under_test, mocker):
    app = app_under_test

    mock_error = mocker.Mock()
    monkeypatch.setattr(talos_app.logger, "error", mock_error)

    app.open_connection("missing")
    mock_error.assert_called_once()
    assert "not found in config" in mock_error.call_args.args[0]


def test_open_connection_uses_config_and_creates_connection(monkeypatch, app_under_test, mocker):
    app = app_under_test
    config = mocker.Mock(socket_port=123, camera_index=0)
    monkeypatch.setitem(talos_app.config.ROBOT_CONFIGS, "host", config)

    # VideoConnection should be created; patch so it doesn't do real IO
    mock_video = mocker.Mock()
    monkeypatch.setattr(talos_app, "VideoConnection", lambda src: mock_video)

    mock_conn = mocker.Mock()
    monkeypatch.setattr(talos_app, "Connection", lambda host, port, video_connection: mock_conn)

    app.open_connection("host")

    assert "host" in app.connections
    assert app.connections["host"] is mock_conn


def test_open_connection_falls_back_when_video_fails(monkeypatch, app_under_test, mocker):
    app = app_under_test
    config = mocker.Mock(socket_port=123, camera_index=0)
    monkeypatch.setitem(talos_app.config.ROBOT_CONFIGS, "host", config)

    # VideoConnection raising should be handled gracefully
    monkeypatch.setattr(talos_app, "VideoConnection", lambda src: (_ for _ in ()).throw(Exception("boom")))

    mock_conn = mocker.Mock()
    monkeypatch.setattr(talos_app, "Connection", lambda host, port, video_connection: mock_conn)

    app.open_connection("host")
    assert "host" in app.connections
    assert app.connections["host"] is mock_conn


def test_start_move_and_discrete_move(monkeypatch, app_under_test, mocker):
    app = app_under_test

    # Setup active connection in manual mode
    publisher = mocker.Mock()
    publisher.polar_pan_discrete = mocker.Mock()

    conn = mocker.Mock(is_manual=True, publisher=publisher)
    app.connections["h"] = conn
    app.connections.set_active("h")

    # Ensure scheduling returns a task we can cancel
    task = mocker.Mock()
    scheduler = app.scheduler
    scheduler.set_interval.return_value = task

    app.control_mode = talos_app.ControlMode.DISCRETE
    app.start_move(talos_app.Direction.UP)

    scheduler.set_interval.assert_called_once()
    assert app.discrete_move_task[talos_app.Direction.UP] is task

    # Running again should not replace the task
    app.start_move(talos_app.Direction.UP)
    assert scheduler.set_interval.call_count == 1

    # Now test discrete_move directly
    app.discrete_move(talos_app.Direction.DOWN)
    publisher.polar_pan_discrete.assert_called_once()


def test_stop_move_continuous_and_stop_all(monkeypatch, app_under_test, mocker):
    app = app_under_test

    publisher = mocker.Mock()
    publisher.polar_pan_continuous_direction_start = mocker.Mock()
    publisher.polar_pan_continuous_stop = mocker.Mock()

    conn = mocker.Mock(is_manual=True, publisher=publisher)
    app.connections["h"] = conn
    app.connections.set_active("h")

    app.control_mode = talos_app.ControlMode.CONTINUOUS
    app.start_move(talos_app.Direction.UP)

    # stop_move should stop when directions cleared
    app.stop_move(talos_app.Direction.UP)
    publisher.polar_pan_continuous_stop.assert_called_once()

    # stop all should call stop even when none are active
    app.stop_all_movement()
    assert publisher.polar_pan_continuous_stop.call_count >= 1


def test_stop_move_discrete_cancels_task(monkeypatch, app_under_test, mocker):
    app = app_under_test
    app.control_mode = talos_app.ControlMode.DISCRETE

    task = mocker.Mock()
    app.discrete_move_task[talos_app.Direction.UP] = task

    app.stop_move(talos_app.Direction.UP)
    task.cancel.assert_called_once()


def test_move_home_uses_publisher(monkeypatch, app_under_test, mocker):
    app = app_under_test
    publisher = mocker.Mock()
    publisher.home = mocker.Mock()

    conn = mocker.Mock(is_manual=True, publisher=publisher)
    app.connections["h"] = conn
    app.connections.set_active("h")

    app.move_home()
    publisher.home.assert_called_once_with(1000)


def test_active_hostname_and_connection_methods(app_under_test, mocker):
    app = app_under_test

    conn = mocker.Mock(host="h")
    app.connections["h"] = conn

    assert app.get_connection_hosts() == ["h"]
    assert app.set_active_connection("h") is conn
    assert app.get_active_connection() is conn
    assert app.get_active_hostname() == "h"

    # Removing non-existent connection returns None
    assert app.disconnect_connection("missing") is None

def test_change_model(monkeypatch, app_under_test, mocker):
   pass