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
        # Админ-чат для ограничений команд и уведомлений
        self.ADMIN_CHAT_ID = _get_env("ADMIN_CHAT_ID")
        if self.ADMIN_CHAT_ID:
            try:
                self.ADMIN_CHAT_ID = int(self.ADMIN_CHAT_ID)
            except Exception:
                pass
        # Публичный URL сервиса для вебхука и опциональный секрет
        self.SERVICE_URL = _get_env("SERVICE_URL_ASSISTANT")
        self.WEBHOOK_SECRET = _get_env("TELEGRAM_WEBHOOK_SECRET")

        # Управление сервисами
        # URL Collector API (например, http://collector:8001)
        self.COLLECTOR_URL = _get_env("COLLECTOR_URL", "http://localhost:8001")
        # URL Aggregator API (опционально, если сервис существует)
        self.AGGREGATOR_URL = _get_env("AGGREGATOR_URL", "http://aggregator:8002")
        # URL Scheduler API (опционально, если сервис существует)
        self.SCHEDULER_URL = _get_env("SCHEDULER_URL", "http://scheduler:8004")
        # URL Classifier API (опционально, если сервис существует)
        self.ASSISTANT_CLASSIFIER_URL = _get_env("CLASSIFIER_URL", "http://classifier:8003")
        # URL Summarizer API (новый сервис)
        self.SUMMARIZER_URL = _get_env("SUMMARIZER_URL", "http://summarizer:8005")
        # URL Publisher API (новый сервис)
        self.PUBLISHER_URL = _get_env("PUBLISHER_URL", "http://publisher:8006")
        self.AGGREGATOR_DIR = os.path.join(self.DATA_DIR, "aggregator")
        self.AGGREGATOR_CONFIG_PATH = os.path.join(self.AGGREGATOR_DIR, "config.json")
        
        # Policy Engine (YAML)
        self.POLICY_DIR = os.path.join(self.DATA_DIR, "policy")
        self.POLICY_CONFIG_PATH = os.path.join(self.POLICY_DIR, "policy.yml")
        # Локальная временная зона для тихих часов
        self.TIMEZONE = _get_env("TIMEZONE", "Asia/Almaty")
        
        # Автопубликация дайджеста после одобрения (совместимо с переменной Collector)
        self.AUTO_PUBLISH_NEWS = (_get_env("AUTO_PUBLISH_NEWS", "1") != "0")


settings = Settings()