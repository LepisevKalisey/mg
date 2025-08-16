"""Logging configuration with sensitive data masking."""

from __future__ import annotations

import logging
from typing import Any, Dict

import structlog


SENSITIVE_FIELDS = {"token", "api_key", "phone", "password", "code"}


def mask_sensitive_data(_: Any, __: Any, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Mask sensitive values in log records."""
    for key in list(event_dict.keys()):
        if key in SENSITIVE_FIELDS and isinstance(event_dict[key], str):
            value = event_dict[key]
            if len(value) > 4:
                event_dict[key] = f"{value[:2]}***{value[-2:]}"
            else:
                event_dict[key] = "***"
    return event_dict


def setup_logging() -> None:
    """Configure structlog with masking processor."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    structlog.configure(
        processors=[
            mask_sensitive_data,
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )


__all__ = ["setup_logging", "mask_sensitive_data", "SENSITIVE_FIELDS"]
