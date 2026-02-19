import platform
from os import path
from typing import Literal

import darkdetect

from src.utils import get_file_path

ASSET_DIRPATH = path.dirname(path.abspath(__file__))


def join_paths(*paths: str) -> str:
    return get_file_path(path.join(ASSET_DIRPATH, *paths))


def get_icon(
    override_is_mac: bool | None = None, override_is_dark_mode: bool | None = None
) -> tuple[str, Literal["icns", "ico"]]:
    """Returns the file path to the correct icon based on the OS and dark mode."""
    is_dark_mode = (
        override_is_dark_mode or darkdetect.isDark()
        if darkdetect.isDark() is not None
        else False
    )
    is_light_mode = (
        override_is_dark_mode is False or darkdetect.isLight()
        if darkdetect.isLight() is not None
        else False
    )
    is_mac = override_is_mac or platform.system() == "Darwin"
    if is_mac and is_dark_mode and not is_light_mode:
        # I'm using an old .icns file because the new macos 26 version has a weird compatibility problem
        # where the icon does not get padding.
        return join_paths("images", "mac-dark-spaced-old.icns"), "icns"
    elif is_mac:
        return join_paths("images", "mac-default-spaced-old.icns"), "icns"
    elif is_dark_mode:
        return join_paths("images", "windows-linux-dark.ico"), "ico"
    return join_paths("images", "windows-linux-light.ico"), "ico"
