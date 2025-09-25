# Classifier service config
import os
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_PATH = os.path.join(BASE_DIR, ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)


def _get_env(name: str, default: str | None = None, required: bool = False) -> str | None:
    v = os.getenv(name)
    if v:
        return v
    if required:
        raise RuntimeError(f"Missing required env var: {name}")
    return default


class Settings:
    def __init__(self) -> None:
        self.HOST = _get_env("CLASSIFIER_HOST", "0.0.0.0")
        self.PORT = int(_get_env("CLASSIFIER_PORT", "8003") or "8003")
        # Toggle simple heuristics (no external LLM at stage 1)
        self.USE_HEURISTICS = (_get_env("CLASSIFIER_USE_HEURISTICS", "1") != "0")
        # Optional: keyword list override (comma-separated)
        kw = _get_env("CLASSIFIER_KEYWORDS", "") or ""
        self.KEYWORDS = [w.strip() for w in kw.split(",") if w.strip()] or [
            "news", "breaking", "urgent", "report:", "reported",
            "срочно", "новость", "источник", "заявил", "пресс-служба",
        ]
        # Minimal length to treat as meaningful content
        self.MIN_TEXT_LEN = int(_get_env("CLASSIFIER_MIN_TEXT_LEN", "50") or "50")


settings = Settings()