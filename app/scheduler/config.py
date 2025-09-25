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
        self.HOST = _get_env("SCHEDULER_HOST", "0.0.0.0")
        self.PORT = int(_get_env("SCHEDULER_PORT", "8004"))
        # Default debounce window seconds
        self.DEBOUNCE_SECONDS = int(_get_env("DEBOUNCE_SECONDS", "60"))
        # Optional URLs for integration
        self.SUMMARIZER_URL = _get_env("SUMMARIZER_URL", "")
        self.PUBLISHER_URL = _get_env("PUBLISHER_URL", "")
        # Temporary integration: call old aggregator.publish_now until Stage 3
        self.AGGREGATOR_URL = _get_env("AGGREGATOR_URL", "http://aggregator:8002")
        # Data paths for reading approved items
        env_data_dir = _get_env("DATA_DIR")
        if env_data_dir:
            self.DATA_DIR = env_data_dir
        else:
            self.DATA_DIR = "/app/data" if os.path.exists("/app/data") else os.path.join(BASE_DIR, "data")
        self.APPROVED_DIR = os.path.join(self.DATA_DIR, "approved")
        # Batch and prompt settings (align with aggregator defaults)
        self.BATCH_LIMIT = int(_get_env("AGG_BATCH_LIMIT", "50"))
        self.SUMMARY_LANGUAGE = _get_env("AGG_LANG", "ru")
        self.TEXT_TRUNCATE_LIMIT = int(_get_env("AGG_TEXT_TRUNCATE_LIMIT", "4000"))


settings = Settings()