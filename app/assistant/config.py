import os
from typing import Optional


def _get_env(name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    val = os.getenv(name, default)
    if required and (val is None or val == ""):
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


# BASE_DIR (корень проекта)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class Settings:
    def __init__(self) -> None:
        # Сетевые настройки сервиса Assistant
        self.HOST = _get_env("ASSISTANT_HOST", "0.0.0.0")
        self.PORT = int(_get_env("ASSISTANT_PORT", "8003"))

        # Директории данных
        env_data_dir = _get_env("DATA_DIR")
        if env_data_dir:
            self.DATA_DIR = env_data_dir
        else:
            self.DATA_DIR = "/app/data" if os.path.exists("/app/data") else os.path.join(BASE_DIR, "data")
        self.PENDING_DIR = os.path.join(self.DATA_DIR, "pending")
        self.APPROVED_DIR = os.path.join(self.DATA_DIR, "approved")

        # Telegram Bot
        self.BOT_TOKEN = _get_env("BOT_TOKEN", required=True)

        # Поллинг Telegram API
        self.POLL_TIMEOUT = int(_get_env("ASSISTANT_POLL_TIMEOUT", "25"))  # long-poll seconds
        self.POLL_INTERVAL = float(_get_env("ASSISTANT_POLL_INTERVAL", "0.5"))  # pause between polls (when empty)


settings = Settings()