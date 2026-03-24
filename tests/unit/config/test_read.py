# TODO: Redo this after App settings manager is merged
import pytest
import yaml

import src.config.read as read_module


def test_read_default_robot_config_uses_local_if_present(tmp_path, monkeypatch):
    local_path = tmp_path / "default_config.local.yaml"
    local_path.write_text(yaml.safe_dump({"test_key": "local"}))

    # Patch module constants so we don't touch repo config files
    monkeypatch.setattr(read_module, "LOCAL_DEFAULT_PATH", str(local_path))
    monkeypatch.setattr(read_module, "DEFAULT_PATH", str(tmp_path / "default_config.yaml"))

    result = read_module.read_default_robot_config()
    assert result == {"test_key": "local"}


def test_read_default_robot_config_uses_default_when_local_missing(tmp_path, monkeypatch):
    default_path = tmp_path / "default_config.yaml"
    default_path.write_text(yaml.safe_dump({"test_key": "default"}))

    monkeypatch.setattr(read_module, "LOCAL_DEFAULT_PATH", str(tmp_path / "does_not_exist.yaml"))
    monkeypatch.setattr(read_module, "DEFAULT_PATH", str(default_path))

    result = read_module.read_default_robot_config()
    assert result == {"test_key": "default"}


def test_read_robot_config_file_returns_empty_when_missing(tmp_path, monkeypatch):
    missing = tmp_path / "robot_configs.yaml"
    monkeypatch.setattr(read_module, "ROBOT_CONFIGS_PATH", str(missing))

    assert read_module.read_robot_config_file() == {}


def test_read_robot_config_file_parses_yaml(tmp_path, monkeypatch):
    cfg_path = tmp_path / "robot_configs.yaml"
    cfg_path.write_text(yaml.safe_dump({"host1": {"foo": "bar"}}))
    monkeypatch.setattr(read_module, "ROBOT_CONFIGS_PATH", str(cfg_path))

    assert read_module.read_robot_config_file() == {"host1": {"foo": "bar"}}


def test_app_settings_recovery_creates_backup_and_writes_default(tmp_path, monkeypatch):
    # Setup existing app settings file and default
    app_settings = tmp_path / "app_settings.local.yaml"
    app_settings.write_text(yaml.safe_dump({"log_level": "INFO"}))
    default_settings = tmp_path / "app_settings.yaml"
    default_settings.write_text(yaml.safe_dump({"log_level": "DEBUG"}))

    monkeypatch.setattr(read_module, "APP_SETTINGS_PATH", str(app_settings))
    monkeypatch.setattr(read_module, "APP_SETTINGS_DEFAULT_PATH", str(default_settings))

    # Ensure backup file does not exist initially
    backup = tmp_path / "app_settings.local.yaml.backup"
    assert not backup.exists()

    # Patch AppSettings to avoid argparse/conflict during tests
    class DummySettings:
        def __init__(self):
            self.log_level = "DEBUG"

    monkeypatch.setattr(read_module, "AppSettings", DummySettings)

    result = read_module.app_settings_recovery()

    assert backup.exists()
    assert result.log_level == "DEBUG"


def test_app_settings_recovery_raises_when_invalid_default(tmp_path, monkeypatch):
    # If the default app settings are invalid, recovery should raise
    invalid_default = tmp_path / "app_settings.yaml"
    invalid_default.write_text("not: valid: yaml: [")

    app_settings = tmp_path / "app_settings.local.yaml"
    app_settings.write_text(yaml.safe_dump({"log_level": "INFO"}))

    monkeypatch.setattr(read_module, "APP_SETTINGS_PATH", str(app_settings))
    monkeypatch.setattr(read_module, "APP_SETTINGS_DEFAULT_PATH", str(invalid_default))

    with pytest.raises(Exception):
        read_module.app_settings_recovery()
