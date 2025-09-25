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
        self.HOST = _get_env("SUMMARIZER_HOST", "0.0.0.0")
        self.PORT = int(_get_env("SUMMARIZER_PORT", "8005"))
        # Gemini
        self.GEMINI_API_KEY = _get_env("GEMINI_API_KEY", required=True)
        self.GEMINI_MODEL_NAME = _get_env("GEMINI_MODEL_NAME", "gemini-1.5-flash")
        # Prompt language and limits
        self.SUMMARY_LANGUAGE = _get_env("SUMMARY_LANGUAGE", "ru")
        self.TEXT_TRUNCATE_LIMIT = int(_get_env("TEXT_TRUNCATE_LIMIT", "4000"))
        # Output paths (keep compatibility with aggregator output)
        env_data_dir = _get_env("DATA_DIR")
        if env_data_dir:
            self.DATA_DIR = env_data_dir
        else:
            self.DATA_DIR = "/app/data" if os.path.exists("/app/data") else os.path.join(BASE_DIR, "data")
        self.OUTPUT_DIR = os.path.join(self.DATA_DIR, "aggregator", "out")
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)
        self.OUTPUT_SUMMARY_FILENAME = _get_env("AGG_SUMMARY_FILENAME", "summary.txt")
        self.SUMMARY_FILE_ENCODING = _get_env("AGG_FILE_ENCODING_RUN", "utf-8")


settings = Settings()