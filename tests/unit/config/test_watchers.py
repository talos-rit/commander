from watchdog.events import FileDeletedEvent

import src.config.watchers.app_settings_file_handler as app_handler_module
import src.config.watchers.robot_config_handler as robot_handler_module


def test_app_settings_replace_reported_as_delete_does_not_back_up(
    monkeypatch, tmp_path
):
    path = tmp_path / "app_settings.local.yaml"
    path.write_text("log_level: INFO\n")
    monkeypatch.setattr(app_handler_module, "APP_SETTINGS_PATH", str(path))
    backups = []
    monkeypatch.setattr(
        app_handler_module, "take_backup_from_app_settings", lambda: backups.append(1)
    )

    app_handler_module.AppSettingFileHandler().on_deleted(FileDeletedEvent(str(path)))

    assert backups == []


def test_app_settings_real_delete_backs_up(monkeypatch, tmp_path):
    path = tmp_path / "app_settings.local.yaml"
    monkeypatch.setattr(app_handler_module, "APP_SETTINGS_PATH", str(path))
    backups = []
    monkeypatch.setattr(
        app_handler_module,
        "take_backup_from_app_settings",
        lambda: backups.append(1) or "backup",
    )

    app_handler_module.AppSettingFileHandler().on_deleted(FileDeletedEvent(str(path)))

    assert backups == [1]


def test_robot_configs_replace_reported_as_delete_reloads(monkeypatch, tmp_path):
    path = tmp_path / "robot_configs.local.yaml"
    path.write_text("{}\n")
    monkeypatch.setattr(robot_handler_module, "ROBOT_CONFIGS_PATH", str(path))
    backups = []
    monkeypatch.setattr(robot_handler_module, "take_backup", lambda: backups.append(1))
    handled = []
    handler = robot_handler_module.RobotConfigFileHandler()
    monkeypatch.setattr(handler, "_handle_config_change", handled.append)

    event = FileDeletedEvent(str(path))
    handler.on_deleted(event)

    assert backups == []
    assert handled == [event]
