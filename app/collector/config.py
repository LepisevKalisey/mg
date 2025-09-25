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

        # Позволяем переопределить директорию сессий отдельно от DATA_DIR
        sess_env = _get_env("SESSIONS_DIR")
        if sess_env:
            self.SESSIONS_DIR = sess_env

        # Editor/admin bot config
        self.BOT_TOKEN = _get_env("BOT_TOKEN")
        self.EDITORS_CHANNEL_ID = _get_env("EDITORS_CHANNEL_ID")
        if self.EDITORS_CHANNEL_ID:
            try:
                self.EDITORS_CHANNEL_ID = int(self.EDITORS_CHANNEL_ID)
            except Exception:
                pass
        # Новый: чат для уведомлений (обычно ADMIN_CHAT_ID ассистента)
        self.ADMIN_CHAT_ID = _get_env("ADMIN_CHAT_ID")
        if self.ADMIN_CHAT_ID:
            try:
                self.ADMIN_CHAT_ID = int(self.ADMIN_CHAT_ID)
            except Exception:
                pass
        # Канал публикации новостей (для мгновенной публикации переписанных новостей)
        self.TARGET_CHANNEL_ID = _get_env("TARGET_CHANNEL_ID")
        if self.TARGET_CHANNEL_ID:
            try:
                self.TARGET_CHANNEL_ID = int(self.TARGET_CHANNEL_ID)
            except Exception:
                pass

        # Gemini config for classification
        self.GEMINI_API_KEY = _get_env("GEMINI_API_KEY")
        self.GEMINI_MODEL_NAME = _get_env("GEMINI_MODEL_NAME", "gemini-1.5-flash")

        # External classifier service URL
        self.CLASSIFIER_URL = _get_env("CLASSIFIER_URL", "http://classifier:8003")

        # Channels list from file or env
        self.CHANNELS_FILE = _get_env("CHANNELS_FILE", os.path.join(self.DATA_DIR, "channels.txt"))
        file_channels = _read_lines_file(self.CHANNELS_FILE)
        env_channels = self._parse_list(_get_env("MONITORING_CHANNELS", ""))
        # Prefer file if present, else env list
        self.MONITORING_CHANNELS = file_channels if file_channels else env_channels

        # Batch size placeholder (not used yet here)
        self.BATCH_SIZE = int(_get_env("BATCH_SIZE", "10"))

        # Простая фильтрация рекламных/партнёрских постов
        # Включена по умолчанию, можно отключить AD_FILTER_ENABLED=0
        self.AD_FILTER_ENABLED = (_get_env("AD_FILTER_ENABLED", "1") != "0")
        # Список ключевых слов/фраз через запятую; если пусто — используются значения по умолчанию в TelegramMonitor
        self.AD_FILTER_WORDS = self._parse_list(_get_env("AD_FILTER_WORDS", ""))

        # Модерационные настройки (по умолчанию включаем классификацию и автопубликацию новостей)
        self.USE_GEMINI_CLASSIFY = (_get_env("USE_GEMINI_CLASSIFY", "1") != "0")
        self.SEND_NEWS_TO_APPROVAL = (_get_env("SEND_NEWS_TO_APPROVAL", "0") != "0")
        self.SEND_OTHERS_TO_APPROVAL = (_get_env("SEND_OTHERS_TO_APPROVAL", "1") != "0")
        self.AUTO_PUBLISH_NEWS = (_get_env("AUTO_PUBLISH_NEWS", "1") != "0")

    @staticmethod
    def _parse_list(value: str) -> List[str]:
        if not value:
            return []
        return [v.strip() for v in value.split(",") if v.strip()]


settings = Settings()