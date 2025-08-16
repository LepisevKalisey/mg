"""Logging configuration using structlog."""
from __future__ import annotations

import logging

try:  # pragma: no cover - structlog might not be installed
    import structlog
except Exception:  # pragma: no cover
    structlog = None  # type: ignore


def setup_logging(level: str = "INFO"):
    """Configure and return a structlog logger.

    Parameters
    ----------
    level:
        Logging level name, e.g. ``"INFO"``.
    """
    if not structlog:
        logging.basicConfig(level=level)
        return logging.getLogger(__name__)

    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger()


__all__ = ["setup_logging"]
