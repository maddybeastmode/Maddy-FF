"""
Advanced Logging Setup
Rich console output + rotating file logs.
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

from rich.logging import RichHandler
from rich.console import Console

from .config_loader import get_config


def setup_logger(name: str = "ffbot") -> logging.Logger:
    """Configure and return a logger instance."""
    config = get_config().settings.logging

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, config.level.upper(), logging.INFO))

    # Clear existing handlers
    logger.handlers = []

    # Rich console handler
    console = Console(stderr=True)
    rich_handler = RichHandler(
        console=console,
        rich_tracebacks=True,
        show_path=False,
        show_time=False,
    )
    rich_handler.setLevel(logging.DEBUG)
    logger.addHandler(rich_handler)

    # File handler with rotation
    log_path = Path(config.file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=config.max_size_mb * 1024 * 1024,
        backupCount=config.backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(config.format))
    logger.addHandler(file_handler)

    return logger
