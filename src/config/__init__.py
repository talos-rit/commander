import src.config.add as add
import src.config.load as load
import src.config.manager as manager
import src.config.path as path
import src.config.read as read
import src.config.watchers.app_settings_file_handler as app_settings_file_handler

__all__ = ["add", "load", "manager", "path", "read"]
# This is not used for type checking, but it shuts up lint for unused imports


def start_app_settings_watchdog():
    manager.FileManager.register_listener(
        path.APP_SETTINGS_PATH, app_settings_file_handler.AppSettingFileHandler()
    )


def __getattr__(name: str):
    if name == "APP_SETTINGS":
        from .__instance import __APP_SETTINGS as APP_SETTINGS

        start_app_settings_watchdog()
        return APP_SETTINGS
    elif name == "ROBOT_CONFIGS":
        from .__instance import __ROBOT_CONFIGS as ROBOT_CONFIGS

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
