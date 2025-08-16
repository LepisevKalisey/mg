"""Common error hierarchy for the project."""
from __future__ import annotations


class MgError(Exception):
    """Base class for all custom errors."""


class ConfigError(MgError):
    """Raised when configuration loading fails."""


class CryptoError(MgError):
    """Raised for cryptographic failures."""


class LLMError(MgError):
    """Errors originating from LLM provider interactions."""


__all__ = ["MgError", "ConfigError", "CryptoError", "LLMError"]
