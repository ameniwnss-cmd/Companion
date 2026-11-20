import logging

LOG_FORMAT = "%(levelname)s:  %(name)s - %(message)s"
HANDLER_NAME = "companion-console"


def configure_logging(level: str) -> None:
    logger = logging.getLogger("companion")
    if not any(handler.get_name() == HANDLER_NAME for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.set_name(HANDLER_NAME)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler)
    logger.setLevel(level.upper())
