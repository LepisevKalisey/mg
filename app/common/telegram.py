"""Telegram helpers for publishing digest messages.

Functions here handle building digest messages with proper
formatting and sending them via a Telegram bot while respecting
Telegram limitations.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, List, Sequence, TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

if TYPE_CHECKING:  # pragma: no cover - only for type checkers
    from aiogram import Bot

UTM_SOURCE = "tg_digest"
UTM_MEDIUM = "post"
CHUNK_LIMIT = 4096


@dataclass
class DigestItem:
    """A single item in a digest."""

    text: str
    url: str
    source_username: str


def add_utm_params(url: str, campaign: date) -> str:
    """Return ``url`` with UTM parameters appended."""
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(
        {
            "utm_source": UTM_SOURCE,
            "utm_medium": UTM_MEDIUM,
            "utm_campaign": campaign.strftime("%Y%m%d"),
        }
    )
    new_query = urlencode(query)
    return urlunparse(parsed._replace(query=new_query))


def append_source_attribution(text: str, username: str) -> str:
    """Append ``(@username)`` attribution to ``text``."""
    return f"{text} (@{username})"


def build_digest(items: Sequence[DigestItem], campaign: date) -> str:
    """Build digest text from ``items`` with attribution and UTM tags."""
    lines: List[str] = []
    for item in items:
        utm_url = add_utm_params(item.url, campaign)
        line = f"• {item.text} <a href=\"{utm_url}\">[link]</a>"
        line = append_source_attribution(line, item.source_username)
        lines.append(line)
    return "\n".join(lines)


def chunk_text(text: str, limit: int = CHUNK_LIMIT) -> List[str]:
    """Split ``text`` into chunks not exceeding ``limit`` characters."""
    chunks: List[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, limit)
        if cut == -1:
            cut = text.rfind(" ", 0, limit)
        if cut == -1:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip()
    return chunks


async def send_html(bot: "Bot", chat_id: int, text: str) -> List[datetime]:
    """Send ``text`` to ``chat_id`` using ``parse_mode=HTML``.

    The message is split into 4096-character chunks. Flood-wait errors
    are handled by waiting and retrying. The ``posted_at`` timestamps
    of successful messages are returned.
    """
    from aiogram.exceptions import TelegramRetryAfter

    posted: List[datetime] = []
    for chunk in chunk_text(text):
        while True:
            try:
                msg = await bot.send_message(chat_id, chunk, parse_mode="HTML")
                posted.append(msg.date)
                break
            except TelegramRetryAfter as e:  # pragma: no cover - network dependent
                await asyncio.sleep(e.retry_after)
    return posted


async def publish_digest(bot: "Bot", chat_id: int, items: Sequence[DigestItem], campaign: date) -> List[datetime]:
    """Build and send digest ``items`` to ``chat_id``.

    Returns list of ``posted_at`` timestamps for sent messages.
    """
    text = build_digest(items, campaign)
    return await send_html(bot, chat_id, text)


__all__ = [
    "DigestItem",
    "add_utm_params",
    "append_source_attribution",
    "build_digest",
    "chunk_text",
    "send_html",
    "publish_digest",
]
