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
        # Имя модели Gemini
        self.GEMINI_MODEL_NAME = _get_env("GEMINI_MODEL_NAME", "gemini-1.5-flash")

        # Токен бота для публикации дайджеста (опционально)
        self.BOT_TOKEN = _get_env("BOT_TOKEN")
        # Целевой канал/чат, куда будет публикация дайджеста (опционально)
        self.TARGET_CHANNEL_ID = _get_env("TARGET_CHANNEL_ID")

        # Настройки Telegram публикации
        self.TELEGRAM_TIMEOUT_SEC = int(_get_env("TELEGRAM_TIMEOUT_SEC", "15"))
        self.TELEGRAM_PARSE_MODE = _get_env("TELEGRAM_PARSE_MODE", "Markdown")
        # Отключить предпросмотр ссылок
        self.TELEGRAM_DISABLE_WEB_PREVIEW = _get_env("TELEGRAM_DISABLE_WEB_PREVIEW", "true").lower() in ("1", "true", "yes", "on")

        # Максимальный размер батча для саммари
        self.BATCH_LIMIT = int(_get_env("AGG_BATCH_LIMIT", "50"))
        # Локаль саммари
        self.SUMMARY_LANGUAGE = _get_env("AGG_LANG", "ru")

        # Параметры вывода
        self.OUTPUT_SUMMARY_FILENAME = _get_env("AGG_SUMMARY_FILENAME", "summary.txt")
        # Кодировки для записи файла в run/publish
        self.SUMMARY_FILE_ENCODING_RUN = _get_env("AGG_FILE_ENCODING_RUN", "utf-8")
        self.SUMMARY_FILE_ENCODING_PUBLISH = _get_env("AGG_FILE_ENCODING_PUBLISH", "utf-8-sig")
        # Лимит усечения текста для промпта
        self.TEXT_TRUNCATE_LIMIT = int(_get_env("AGG_TEXT_TRUNCATE_LIMIT", "4000"))

        # Автодебаунс публикации (секунды ожидания перед батчевой публикацией)
        self.DEBOUNCE_SECONDS = int(_get_env("AGG_DEBOUNCE_SECONDS", "60"))
        # URL Scheduler API (новый сервис для дебаунса)
        self.SCHEDULER_URL = _get_env("SCHEDULER_URL", "http://scheduler:8004")


settings = Settings()