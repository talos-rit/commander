import pytest
import yaml
from pydantic import ValidationError

import src.config as config_module
import src.config.read as read_module
import src.config.save as save_module
from src.config.schema.app import AppSettings, AppSettingsFields
from src.config.schema.robot import ConnectionConfig


@pytest.fixture
def paths(monkeypatch, tmp_path):
    app_path = tmp_path / "app_settings.local.yaml"
    robot_path = tmp_path / "robot_configs.local.yaml"
    monkeypatch.setattr(save_module, "APP_SETTINGS_PATH", str(app_path))
    monkeypatch.setattr(save_module, "ROBOT_CONFIGS_PATH", str(robot_path))
    monkeypatch.setattr(read_module, "ROBOT_CONFIGS_PATH", str(robot_path))
    monkeypatch.setattr(config_module, "APP_SETTINGS", AppSettingsFields(), raising=False)
    monkeypatch.setattr(config_module, "ROBOT_CONFIGS", {}, raising=False)
    return app_path, robot_path


def test_save_app_settings_writes_only_changed_keys_and_applies(paths):
    app_path, _ = paths
    app_path.write_text("log_level: DEBUG\nbbox_max_fps: 60\n")

    result = save_module.save_app_settings({"ui_mode": "debug", "camera_1_host": "bluey"})

    assert isinstance(result, AppSettings)
    assert config_module.APP_SETTINGS.ui_mode == "debug"
    assert config_module.APP_SETTINGS.camera_1_host == "bluey"
    saved = yaml.safe_load(app_path.read_text())
    assert saved == {
        "log_level": "DEBUG",
        "bbox_max_fps": 60,
        "ui_mode": "debug",
        "camera_1_host": "bluey",
    }


def test_save_app_settings_creates_missing_file(paths):
    app_path, _ = paths

    save_module.save_app_settings({"web_port": 9001})

    assert yaml.safe_load(app_path.read_text()) == {"web_port": 9001}


def test_save_app_settings_rejects_invalid_and_leaves_file_alone(paths):
    app_path, _ = paths
    app_path.write_text("log_level: INFO\n")

    with pytest.raises(ValidationError):
        save_module.save_app_settings({"display_mode": "three_screen"})

    assert app_path.read_text() == "log_level: INFO\n"
    assert config_module.APP_SETTINGS.display_mode == "one_screen"


def test_update_config_replaces_existing_entry(paths):
    _, robot_path = paths
    robot_path.write_text(
        yaml.safe_dump(
            {
                "a": {"socket_host": "a", "socket_port": 1, "camera_index": 0},
                "b": {"socket_host": "b", "socket_port": 2, "camera_index": 1},
            }
        )
    )
    new = ConnectionConfig(socket_host="a", socket_port=99, camera_index="rtsp://a")

    save_module.update_config("a", new)

    saved = yaml.safe_load(robot_path.read_text())
    assert saved["a"]["socket_port"] == 99
    assert saved["b"]["socket_port"] == 2
    assert config_module.ROBOT_CONFIGS["a"] is new


def test_remove_config(paths):
    _, robot_path = paths
    robot_path.write_text(
        yaml.safe_dump({"a": {"socket_host": "a", "socket_port": 1, "camera_index": 0}})
    )
    config_module.ROBOT_CONFIGS["a"] = object()

    assert save_module.remove_config("a") is True
    assert yaml.safe_load(robot_path.read_text()) == {}
    assert "a" not in config_module.ROBOT_CONFIGS
    assert save_module.remove_config("a") is False


def test_app_settings_fields_defaults_keep_single_camera_setup():
    fields = AppSettingsFields()
    assert fields.camera_2_host is None
    assert fields.display_mode == "one_screen"
    assert fields.ui_mode == "debug"
    assert fields.web_host == "127.0.0.1"
