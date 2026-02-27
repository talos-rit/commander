from loguru import logger

from .config.load import APP_SETTINGS


def configure_logger(remove_existing: bool = False, process_name: str = "log"):
    if remove_existing:
        # Shuts up console output for loguru
        logger.remove()
    logger.add(
        f".log/{process_name}_{{time}}.log",
        enqueue=True,
        retention=5,
        level=APP_SETTINGS.log_level,
    )
