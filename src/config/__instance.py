"""This is a module that holds global reference to the settings and configs loaded from disk.

This might be too much considering we are enforcing lazy loading, but I wanted to enforce a really protected module.
"""

from .load import load_app_settings, load_robot_config

__APP_SETTINGS = load_app_settings()
__ROBOT_CONFIGS = load_robot_config()

__all__ = ["__APP_SETTINGS", "__ROBOT_CONFIGS"]
