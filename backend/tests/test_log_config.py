import logging

from companion.log_config import HANDLER_NAME, configure_logging


def test_logging_is_configured_once_at_the_requested_level() -> None:
    configure_logging("debug")
    configure_logging("warning")

    logger = logging.getLogger("companion")
    assert logger.level == logging.WARNING
    assert [h.get_name() for h in logger.handlers].count(HANDLER_NAME) == 1
