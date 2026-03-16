import src.config.add as add
import src.config.load as load
import src.config.manager as manager
import src.config.path as path
import src.config.read as read
import src.config.watchers.app_settings_file_handler as app_settings_file_handler
import src.config.watchers.robot_config_handler as robot_config_handler

__all__ = ["add", "load", "manager", "path", "read"]
# This is not used for type checking, but it shuts up lint for unused imports

WATCHDOG_STARTED = dict()
APP_SETTINGS_FILE_HANDLER = app_settings_file_handler.AppSettingFileHandler()
ROBOT_CONFIG_FILE_HANDLER = robot_config_handler.RobotConfigFileHandler()
register_robot_config_observer = robot_config_handler.register_listener(
    ROBOT_CONFIG_FILE_HANDLER
)
"""Use this to register a callback to be called when the robot config file is modified or deleted. 
The callback should take in a FileModifiedEvent or DirModifiedEvent as an argument."""


def _start_app_settings_watchdog():
    """This is automatically called when the app settings are first accessed, so don't call this manually."""
    if WATCHDOG_STARTED.get("app_settings", False):
        return
    WATCHDOG_STARTED["app_settings"] = True
    manager.FileManager.register_listener(
        path.APP_SETTINGS_PATH, APP_SETTINGS_FILE_HANDLER
    )


def _start_robot_configs_watchdog():
    """This is automatically called when the robot configs are first accessed, so don't call this manually."""
    if WATCHDOG_STARTED.get("robot_configs", False):
        return
    WATCHDOG_STARTED["robot_configs"] = True
    manager.FileManager.register_listener(
        path.ROBOT_CONFIGS_PATH, ROBOT_CONFIG_FILE_HANDLER
    )


def __getattr__(name: str):
    if name == "APP_SETTINGS":
        from .__instance import __APP_SETTINGS as APP_SETTINGS

        _start_app_settings_watchdog()
        return APP_SETTINGS
    elif name == "ROBOT_CONFIGS":
        from .__instance import __ROBOT_CONFIGS as ROBOT_CONFIGS

        _start_robot_configs_watchdog()
        return ROBOT_CONFIGS
    elif name == "__instance":
        raise AttributeError(f"module '{__name__}' has no attribute '__instance'")
    else:
        return globals()[name]


def __setattr__(name, value):
    """
    While we really don't care about the app settings being reloaded, for consistency I am going to add this here for both app settings and robot configs.
    Just in case we want to add reloading functionality without killing the process.
    """
    if name == "APP_SETTINGS":
        from . import __instance as instance

        instance.__APP_SETTINGS = value
        return instance.__APP_SETTINGS
    elif name == "ROBOT_CONFIGS":
        from . import __instance as instance

        instance.__ROBOT_CONFIGS = value
        return instance.__ROBOT_CONFIGS
    else:
        globals()[name] = value
        return value


def __dir__():
    return __all__ + ["APP_SETTINGS", "ROBOT_CONFIGS"]
