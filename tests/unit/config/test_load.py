# TODO: Re-test this after App settings manager is merged
import builtins

import pytest

import src.config.load as load_module
from pydantic import ValidationError


class DummySettings:
    """A lightweight stand-in for AppSettings used in tests."""

    def model_dump_json(self, indent: int = 2):
        return "{}"


def test_load_app_settings_returns_settings_when_valid(monkeypatch):
    dummy = DummySettings()
    monkeypatch.setattr(load_module, "AppSettings", lambda: dummy)

    assert load_module.load_app_settings() is dummy


def _raise_validation_error():
    raise ValidationError("validation error", [])


def test_load_app_settings_asks_for_input_and_uses_recovery(monkeypatch):
    monkeypatch.setattr(load_module, "AppSettings", _raise_validation_error)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "y")

    recovered = object()

    assert load_module.load_app_settings(_recovery_method=lambda: recovered) is recovered


def test_load_app_settings_raises_when_user_declines(monkeypatch):
    monkeypatch.setattr(load_module, "AppSettings", _raise_validation_error)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "n")

    with pytest.raises(ValidationError):
        load_module.load_app_settings(_recovery_method=lambda: object())


def test_load_default_robot_config_propagates_validation_error(monkeypatch):
    monkeypatch.setattr(load_module, "read_default_robot_config", lambda: {"bad": "data"})

    with pytest.raises(ValidationError):
        load_module.load_default_robot_config()

def test_load_robot_config_skips_invalid_hosts(monkeypatch):
    class DummyConnection:
        def __init__(self, **kwargs):
            if kwargs.get("foo") == "bad":
                raise ValidationError("invalid", [])

    monkeypatch.setattr(load_module, "ConnectionConfig", DummyConnection)

    # Provide default config to allow merge
    monkeypatch.setattr(load_module, "DEFAULT_ROBOT_CONFIG", type("D", (), {"model_dump": lambda self: {}})())

    monkeypatch.setattr(load_module, "read_robot_config_file", lambda: {"good": {"foo": "ok"}, "bad": {"foo": "bad"}})

    result = load_module.load_robot_config()
    assert "good" in result
    assert "bad" not in result
