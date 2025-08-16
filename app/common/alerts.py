"""Alerting hooks for notable error conditions."""

from __future__ import annotations

import structlog

from .metrics import LLM_ERRORS_TOTAL, PUBLISH_FAILURES_TOTAL

logger = structlog.get_logger()


def alert_master_session_invalid() -> None:
    """Alert when the master session becomes invalid."""
    logger.error("master_session_invalid")


def alert_llm_circuit_breaker() -> None:
    """Alert when the LLM circuit breaker is triggered."""
    LLM_ERRORS_TOTAL.inc()
    logger.error("llm_circuit_breaker_triggered")


def alert_digest_publication_failure() -> None:
    """Alert when digest publication fails."""
    PUBLISH_FAILURES_TOTAL.inc()
    logger.error("digest_publication_failure")


def alert_empty_release() -> None:
    """Alert when a scheduled digest has no items to publish."""
    logger.warning("empty_digest_release")


__all__ = [
    "alert_master_session_invalid",
    "alert_llm_circuit_breaker",
    "alert_digest_publication_failure",
    "alert_empty_release",
]
