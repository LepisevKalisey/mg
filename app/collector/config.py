import os
from typing import Optional, List

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _get_env(name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    val = os.getenv(name, default)
    if required and (val is None or val == ""):
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _parse_channels(raw: Optional[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for item in (raw or "").replace("\r", "\n").split("\n"):
        for part in item.split(','):
            ch = part.strip()
            if not ch:
                continue
            if not (ch.startswith("@") or ch.startswith("https://t.me/")):
                ch = "@" + ch
            if ch not in seen:
                result.append(ch)
                seen.add(ch)
    return result


class Settings:
    def __init__(self) -> None:
        # Сетевые настройки сервиса Collector (может использоваться внешним раннером)
        self.HOST = _get_env("COLLECTOR_HOST", "0.0.0.0")
        self.PORT = int(_get_env("COLLECTOR_PORT", "8001"))

        # Директории данных
        env_data_dir = _get_env("DATA_DIR")
        if env_data_dir:
            self.DATA_DIR = env_data_dir
        else:
            self.DATA_DIR = "/app/data" if os.path.exists("/app/data") else os.path.join(BASE_DIR, "data")
        self.PENDING_DIR = os.path.join(self.DATA_DIR, "pending")
        self.APPROVED_DIR = os.path.join(self.DATA_DIR, "approved")
        self.SESSIONS_DIR = os.path.join(self.DATA_DIR, "sessions")

        # Файл со списком каналов для мониторинга
        self.CHANNELS_FILE = _get_env("CHANNELS_FILE", os.path.join(self.DATA_DIR, "collector", "channels.txt"))
        # Список каналов: сначала из переменной окружения, затем из файла (если существует)
        env_channels = _get_env("MONITORING_CHANNELS")
        channels: List[str] = _parse_channels(env_channels)
        if not channels and self.CHANNELS_FILE and os.path.exists(self.CHANNELS_FILE):
            try:
                with open(self.CHANNELS_FILE, "r", encoding="utf-8") as f:
                    file_raw = f.read()
                    channels = _parse_channels(file_raw)
            except Exception:
                channels = []
        self.MONITORING_CHANNELS = channels

        # Telegram MTProto API credentials (обязательные)
        api_id_str = _get_env("API_ID") or _get_env("TELEGRAM_API_ID")
        api_hash = _get_env("API_HASH") or _get_env("TELEGRAM_API_HASH")
        if not api_id_str or not api_hash:
            raise RuntimeError("Missing required Telegram API credentials: API_ID/API_HASH")
        try:
            self.API_ID = int(api_id_str)
        except Exception:
            # Если не число — оставляем строку как есть (Telethon ожидает int, но дадим явную ошибку позже)
            raise RuntimeError("API_ID must be an integer")
        self.API_HASH = api_hash

        # Telegram Bot для уведомлений редакторов/админа (опционально)
        self.BOT_TOKEN = _get_env("BOT_TOKEN")
        # Канал/чат редакторов, куда будут уходить заявки на одобрение
        self.EDITORS_CHANNEL_ID = _get_env("EDITORS_CHANNEL_ID")
        if self.EDITORS_CHANNEL_ID:
            try:
                self.EDITORS_CHANNEL_ID = int(self.EDITORS_CHANNEL_ID)
            except Exception:
                # оставляем строку, если это @username; Telegram API допустит такое значение
                pass
        # Админ-чат для уведомлений об авторизации
        self.ADMIN_CHAT_ID = _get_env("ADMIN_CHAT_ID")
        if self.ADMIN_CHAT_ID:
            try:
                self.ADMIN_CHAT_ID = int(self.ADMIN_CHAT_ID)
            except Exception:
                pass
        # Номер телефона для авторизации (опционально)
        self.PHONE_NUMBER = _get_env("PHONE_NUMBER")

        # URL классификатора (новый сервис)
        self.CLASSIFIER_URL = _get_env("CLASSIFIER_URL", "http://classifier:8003")

        # Флаги авто-одобрения/классификации (могут динамически меняться через API)
        self.USE_GEMINI_CLASSIFY = _get_bool("USE_GEMINI_CLASSIFY", True)
        self.SEND_NEWS_TO_APPROVAL = _get_bool("SEND_NEWS_TO_APPROVAL", True)
        self.SEND_OTHERS_TO_APPROVAL = _get_bool("SEND_OTHERS_TO_APPROVAL", True)
        self.AUTO_PUBLISH_NEWS = _get_bool("AUTO_PUBLISH_NEWS", True)

        # Фильтр рекламы
        self.AD_FILTER_ENABLED = _get_bool("AD_FILTER_ENABLED", True)
        raw_words = _get_env("AD_FILTER_WORDS")
        if raw_words:
            self.AD_FILTER_WORDS = [w.strip() for w in raw_words.split(',') if w.strip()]
        else:
            self.AD_FILTER_WORDS = None


settings = Settings()