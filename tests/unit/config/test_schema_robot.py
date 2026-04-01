import pytest
from pydantic import ValidationError

from src.config.schema.robot import ConnectionConfig


def _valid_payload(**overrides):
    payload = {
        "socket_host": "robot.local",
        "socket_port": 5000,
        "camera_index": 0,
    }
    payload.update(overrides)
    return payload


def test_connection_config_accepts_valid_defaults():
    config = ConnectionConfig(**_valid_payload())

    assert config.socket_host == "robot.local"
    assert config.socket_port == 5000
    assert config.camera_index == 0


def test_connection_config_strips_socket_host_whitespace():
    config = ConnectionConfig(**_valid_payload(socket_host="  robot.local  "))

    assert config.socket_host == "robot.local"


@pytest.mark.parametrize("camera_index", ["rtsp://camera/stream", "http://camera/stream"])
def test_connection_config_accepts_camera_url(camera_index):
    config = ConnectionConfig(**_valid_payload(camera_index=camera_index))

    assert config.camera_index == camera_index


@pytest.mark.parametrize(
    "field,value",
    [
        ("socket_port", 0),
        ("socket_port", 70000),
        ("acceptable_box_percent", 0.0),
        ("acceptable_box_percent", 1.1),
        ("vertical_field_of_view", 0),
        ("horizontal_field_of_view", 181),
        ("fps", 0),
    ],
)
def test_connection_config_rejects_out_of_range_values(field, value):
    with pytest.raises(ValidationError):
        ConnectionConfig(**_valid_payload(**{field: value}))


@pytest.mark.parametrize(
    "camera_index",
    [-1, "", "   ", 1.5, None],
)
def test_connection_config_rejects_invalid_camera_index(camera_index):
    with pytest.raises(ValidationError):
        ConnectionConfig(**_valid_payload(camera_index=camera_index))
