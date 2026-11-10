"""Sistema de Logging nativo do Python para o UNION MONEY AI."""

import logging
from logging.handlers import RotatingFileHandler
import sys
from app.config import settings


def setup_logging() -> logging.Logger:
    """Configura logger central com saída em console e arquivo rotativo."""
    logger = logging.getLogger("union_money_ai")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(module)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    log_file = settings.logs_dir / "union_money_ai.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


logger = setup_logging()

