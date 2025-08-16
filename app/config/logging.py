"""Logging configuration module."""

import logging
import logging.config
import os
from pathlib import Path
from typing import Dict, Any, Optional

from app.config import get_config


def setup_logging(config_path: Optional[str] = None) -> None:
    """Set up logging configuration.

    Args:
        config_path: Path to the logging configuration file.
            If not provided, will use the configuration from the config module.
    """
    if config_path is not None and os.path.exists(config_path):
        # Load configuration from file
        logging.config.fileConfig(config_path, disable_existing_loggers=False)
    else:
        # Load configuration from config module
        config = get_config()
        logging_config = config.get_logging_config()
        if logging_config:
            # Create logs directory if it doesn't exist
            _ensure_log_directory(logging_config)
            # Configure logging
            logging.config.dictConfig(logging_config)
        else:
            # Fallback to basic configuration
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            )


def _ensure_log_directory(logging_config: Dict[str, Any]) -> None:
    """Ensure that the log directory exists.

    Args:
        logging_config: Logging configuration dictionary.
    """
    # Check handlers for file paths
    handlers = logging_config.get("handlers", {})
    for handler_config in handlers.values():
        if "filename" in handler_config:
            log_file = handler_config["filename"]
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name.

    Args:
        name: Logger name.

    Returns:
        Logger instance.
    """
    return logging.getLogger(name)