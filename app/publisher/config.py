import os
from typing import Optional

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _get_env(name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    val = os.getenv(name, default)
    if required and (val is None or val == ""):
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


class Settings:
    def __init__(self) -> None:
        self.HOST = _get_env("PUBLISHER_HOST", "0.0.0.0")
        self.PORT = int(_get_env("PUBLISHER_PORT", "8006"))
        # Telegram
        self.BOT_TOKEN = _get_env("BOT_TOKEN")
        self.TARGET_CHANNEL_ID = _get_env("TARGET_CHANNEL_ID")
        self.TELEGRAM_TIMEOUT_SEC = int(_get_env("TELEGRAM_TIMEOUT_SEC", "15"))
        self.TELEGRAM_PARSE_MODE = _get_env("TELEGRAM_PARSE_MODE", "Markdown")
        self.TELEGRAM_DISABLE_WEB_PREVIEW = _get_env("TELEGRAM_DISABLE_WEB_PREVIEW", "true").lower() in ("1", "true", "yes", "on")
        # Output dirs (optional compatibility)
        env_data_dir = _get_env("DATA_DIR")
        if env_data_dir:
            self.DATA_DIR = env_data_dir
        else:
            self.DATA_DIR = "/app/data" if os.path.exists("/app/data") else os.path.join(BASE_DIR, "data")
        self.OUTPUT_DIR = os.path.join(self.DATA_DIR, "aggregator", "out")
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)


settings = Settings()