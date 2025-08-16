"""Miscellaneous helper utilities."""
from __future__ import annotations

import html
import re


_URL_RE = re.compile(r"https?://[^\s>'\"]+")


def extract_links(text: str) -> list[str]:
    """Return all ``http``/``https`` links found in ``text``.

    The parser is intentionally simple and based on a regular expression that
    ignores trailing punctuation and surrounding markup. It is sufficient for
    unit tests and lightweight parsing in the prototype.
    """
    return _URL_RE.findall(text)


def split_topics(text: str) -> list[str]:
    """Split ``text`` into topics using blank lines as separators.

    This mirrors the first heuristic described in the technical specification:
    an empty line denotes a new topic. The function trims whitespace and
    discards empty chunks.
    """
    parts = [part.strip() for part in re.split(r"\n\s*\n", text.strip())]
    return [p for p in parts if p]


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


__all__ = [
    "html_escape",
    "count_tokens",
    "calculate_cost",
    "extract_links",
    "split_topics",
]
