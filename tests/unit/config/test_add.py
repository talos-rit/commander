import pytest
import yaml

import src.config.add as add_module
from src.config.schema.robot import ConnectionConfig


def test_add_config_writes_to_file_and_updates_global(monkeypatch, tmp_path):
    # Set up a clean global map and temp file
    monkeypatch.setattr(add_module.global_config, "ROBOT_CONFIGS", {})
    temp_file = tmp_path / "robot_configs.yaml"
    monkeypatch.setattr(add_module, "ROBOT_CONFIGS_PATH", str(temp_file))

    config = ConnectionConfig(socket_host="host1", socket_port=1234, camera_index=0)
    add_module.add_config(config)

    assert "host1" in add_module.global_config.ROBOT_CONFIGS
    assert add_module.global_config.ROBOT_CONFIGS["host1"].socket_port == 1234

    # File should contain a YAML mapping for the new host
    loaded = yaml.safe_load(temp_file.read_text())
    assert loaded == {"host1": config.model_dump()}


@pytest.mark.parametrize(
    "socket_host,socket_port,camera_index,expected_error",
    [
        ("", 1234, 0, "Host must be a non-empty string"),
        ("host1", "not-a-number", 0, "Port must be a valid integer"),
        ("host1", 1234, "", "Camera URL cannot be empty string"),
    ],
)
def test_validate_connection_config_invalid_inputs(socket_host, socket_port, camera_index, expected_error, monkeypatch):
    # Ensure no existing entries to avoid "already exists" error
    monkeypatch.setattr(add_module.global_config, "ROBOT_CONFIGS", {})

    valid, cfg, errors = add_module.validate_connection_config(socket_host, socket_port, camera_index)

    assert not valid
    assert cfg is None
    assert any(expected_error in e for e in errors)


def test_validate_connection_config_duplicate_host(monkeypatch):
    monkeypatch.setattr(add_module.global_config, "ROBOT_CONFIGS", {"host1": object()})

    valid, cfg, errors = add_module.validate_connection_config("host1", 1234, 0)

    assert not valid
    assert cfg is None
    assert "already exists" in " ".join(errors)


def test_validate_connection_config_success(monkeypatch):
    monkeypatch.setattr(add_module.global_config, "ROBOT_CONFIGS", {})

    valid, cfg, errors = add_module.validate_connection_config("host2", "5678", 0)

    assert valid
    assert errors == []
    assert isinstance(cfg, ConnectionConfig)
    assert cfg.socket_host == "host2"
    assert cfg.socket_port == 5678
