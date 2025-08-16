"""Abstraction over various LLM providers with retry logic."""
from __future__ import annotations

import os
import time
from typing import Any, Dict

try:  # pragma: no cover - optional dependency
    import requests
except Exception:  # pragma: no cover - requests might be missing
    requests = None  # type: ignore

from .errors import LLMError


class LLMClient:
    """Small helper around different LLM providers.

    Parameters
    ----------
    provider:
        Name of the provider, e.g. ``"openai"``.
    model:
        Model identifier to use when sending requests.
    api_key:
        API key for the provider; if omitted, environment variables are
        consulted (``OPENAI_API_KEY`` or ``ANTHROPIC_API_KEY``).
    retries:
        Number of times to retry a failing request with exponential backoff.
    """

    def __init__(
        self, provider: str, model: str, api_key: str | None = None, retries: int = 3
    ) -> None:
        self.provider = provider.lower()
        self.model = model
        self.api_key = api_key or os.getenv(f"{self.provider.upper()}_API_KEY")
        self.retries = max(1, retries)

    # ---- public API -------------------------------------------------
    def complete(self, prompt: str, **kwargs: Any) -> str:
        """Send a completion request and return the text response."""
        for attempt in range(1, self.retries + 1):
            try:
                if self.provider == "openai":
                    return self._openai_complete(prompt, **kwargs)
                if self.provider == "anthropic":
                    return self._anthropic_complete(prompt, **kwargs)
                raise LLMError(f"Unknown provider: {self.provider}")
            except Exception as exc:
                if attempt >= self.retries:
                    raise LLMError(str(exc)) from exc
                time.sleep(2 ** attempt)
        raise LLMError("Exhausted retries")

    # ---- provider implementations ----------------------------------
    def _openai_complete(self, prompt: str, **kwargs: Any) -> str:
        if not requests:
            raise LLMError("requests library not available")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        payload.update(kwargs)
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions", json=payload, headers=headers
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def _anthropic_complete(self, prompt: str, **kwargs: Any) -> str:
        if not requests:
            raise LLMError("requests library not available")
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "max_tokens_to_sample": kwargs.get("max_tokens", 256),
        }
        resp = requests.post(
            "https://api.anthropic.com/v1/complete", json=payload, headers=headers
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("completion", "")


__all__ = ["LLMClient", "LLMError"]
