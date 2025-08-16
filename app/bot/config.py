from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List


@dataclass
class Settings:
    """Application settings loaded from environment variables."""

    bot_token: str
    admin_ids: List[int]
    http_host: str = "0.0.0.0"
    http_port: int = 8080


def load_settings() -> Settings:
    """Load :class:`Settings` from environment variables.

    Environment variables:
        BOT_TOKEN: Telegram bot token.
        ADMIN_IDS: Comma separated list of administrator Telegram user IDs.
        HTTP_HOST: Host for health/metrics server. Defaults to 0.0.0.0.
        HTTP_PORT: Port for health/metrics server. Defaults to 8080.
    """

    bot_token = os.getenv("BOT_TOKEN", "")
    raw_admins = os.getenv("ADMIN_IDS", "")
    admin_ids = [int(x) for x in raw_admins.split(",") if x.strip()]
    http_host = os.getenv("HTTP_HOST", "0.0.0.0")
    http_port = int(os.getenv("HTTP_PORT", "8080"))
    return Settings(
        bot_token=bot_token,
        admin_ids=admin_ids,
        http_host=http_host,
        http_port=http_port,
    )


__all__ = ["Settings", "load_settings"]
