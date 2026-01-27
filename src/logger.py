from loguru import logger


def configure_logger(remove_existing: bool = False, process_name: str = "log"):
    if remove_existing:
        # Shuts up console output for loguru
        logger.remove()
    logger.add(
        f".log/{process_name}_{{time}}.log",
        enqueue=True,
        level="DEBUG",
    )

    class StreamToLoguru:
        def write(self, message):
            message = message.strip()
            if message:
                logger.info(message)

        def flush(self):
            pass  # Needed for file-like API

    # sys.stdout = StreamToLoguru()
    # sys.stderr = StreamToLoguru()
