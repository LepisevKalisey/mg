import os
from typing import List


def _get_env(name: str, default: str | None = None, required: bool = False) -> str | None:
    val = os.getenv(name, default)
    if required and (val is None or val == ""):
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


def _read_lines_file(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    except FileNotFoundError:
        return []


# Определим BASE_DIR (корень проекта)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class Settings:
    def __init__(self) -> None:
        # Telegram user credentials
        self.API_ID = int(_get_env("API_ID", required=True))
        self.API_HASH = _get_env("API_HASH", required=True)
        # PHONE_NUMBER optional (only for first-time auth); support PHONE for compatibility
        self.PHONE_NUMBER = _get_env("PHONE_NUMBER") or _get_env("PHONE")

        # Service config
        self.HOST = _get_env("COLLECTOR_HOST", "0.0.0.0")
        self.PORT = int(_get_env("COLLECTOR_PORT", "8001"))

        # Data directories
        env_data_dir = _get_env("DATA_DIR")
        if env_data_dir:
            self.DATA_DIR = env_data_dir
        else:
            # В контейнере путь /app/data создаётся Dockerfile-ом, используем его если существует,
            # иначе по умолчанию data/ в корне проекта (для локального запуска)
            self.DATA_DIR = "/app/data" if os.path.exists("/app/data") else os.path.join(BASE_DIR, "data")
        self.PENDING_DIR = os.path.join(self.DATA_DIR, "pending")
        self.APPROVED_DIR = os.path.join(self.DATA_DIR, "approved")
        self.SESSIONS_DIR = os.path.join(self.DATA_DIR, "sessions")

        # Editor bot config
        self.BOT_TOKEN = _get_env("BOT_TOKEN")
        self.EDITORS_CHANNEL_ID = _get_env("EDITORS_CHANNEL_ID")
        if self.EDITORS_CHANNEL_ID:
            try:
                self.EDITORS_CHANNEL_ID = int(self.EDITORS_CHANNEL_ID)
            except Exception:
                pass

        # Channels list from file or env
        self.CHANNELS_FILE = _get_env("CHANNELS_FILE", os.path.join(self.DATA_DIR, "channels.txt"))
        file_channels = _read_lines_file(self.CHANNELS_FILE)
        env_channels = self._parse_list(_get_env("MONITORING_CHANNELS", ""))
        # Prefer file if present, else env list
        self.MONITORING_CHANNELS = file_channels if file_channels else env_channels

        # Batch size placeholder (not used yet here)
        self.BATCH_SIZE = int(_get_env("BATCH_SIZE", "10"))

    @staticmethod
    def _parse_list(value: str) -> List[str]:
        if not value:
            return []
        return [v.strip() for v in value.split(",") if v.strip()]


settings = Settings()