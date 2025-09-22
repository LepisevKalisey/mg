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
        self.HOST = _get_env("AGGREGATOR_HOST", "0.0.0.0")
        self.PORT = int(_get_env("AGGREGATOR_PORT", "8002"))

        env_data_dir = _get_env("DATA_DIR")
        if env_data_dir:
            self.DATA_DIR = env_data_dir
        else:
            self.DATA_DIR = "/app/data" if os.path.exists("/app/data") else os.path.join(BASE_DIR, "data")
        self.PENDING_DIR = os.path.join(self.DATA_DIR, "pending")
        self.APPROVED_DIR = os.path.join(self.DATA_DIR, "approved")
        self.OUTPUT_DIR = os.path.join(self.DATA_DIR, "aggregator", "out")
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)

        # Ключ Gemini
        self.GEMINI_API_KEY = _get_env("GEMINI_API_KEY", required=True)
        # Токен бота для публикации дайджеста (опционально)
        self.BOT_TOKEN = _get_env("BOT_TOKEN")
        # Целевой канал/чат, куда будет публикация дайджеста (опционально)
        self.TARGET_CHANNEL_ID = _get_env("TARGET_CHANNEL_ID")
        # Максимальный размер батча для саммари
        self.BATCH_LIMIT = int(_get_env("AGG_BATCH_LIMIT", "50"))
        # Локаль саммари
        self.SUMMARY_LANGUAGE = _get_env("AGG_LANG", "ru")


settings = Settings()