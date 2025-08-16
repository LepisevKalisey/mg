"""Miscellaneous helper utilities."""
from __future__ import annotations

import html
import re


def html_escape(text: str) -> str:
    """HTML escape ``text`` using :func:`html.escape`."""
    return html.escape(text, quote=True)


def count_tokens(text: str) -> int:
    """Very small tokenizer splitting on words and punctuation.

    This is **not** an exact replication of any provider's tokenizer but
    serves as a cheap approximation.
    """
    return len(re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE))


def calculate_cost(token_count: int, rate_per_1k: float) -> float:
    """Return monetary cost given ``rate_per_1k`` price."""
    return (token_count / 1000.0) * rate_per_1k


__all__ = ["html_escape", "count_tokens", "calculate_cost"]
