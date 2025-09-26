# Classifier service config
import os
from typing import Optional, List
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_PATH = os.path.join(BASE_DIR, ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)


def _get_env(name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    v = os.getenv(name)
    if v is not None and v != "":
        return v
    if required:
        raise RuntimeError(f"Missing required env var: {name}")
    return default


class Settings:
    def __init__(self) -> None:
        # Network
        self.HOST = _get_env("CLASSIFIER_HOST", "0.0.0.0")
        self.PORT = int(_get_env("CLASSIFIER_PORT", "8003") or "8003")

        # Gemini (optional: fallback to heuristics if not set)
        self.GEMINI_API_KEY = _get_env("GEMINI_API_KEY")
        self.GEMINI_MODEL_NAME = _get_env("GEMINI_MODEL_NAME", "gemini-1.5-flash")

        # Heuristics / legacy
        self.USE_HEURISTICS = (_get_env("CLASSIFIER_USE_HEURISTICS", "1") != "0")
        kw = _get_env("CLASSIFIER_KEYWORDS", "") or ""
        self.KEYWORDS = [w.strip() for w in kw.split(",") if w.strip()] or [
            "news", "breaking", "urgent", "report:", "reported",
            "срочно", "новость", "источник", "заявил", "пресс-служба",
        ]
        self.MIN_TEXT_LEN = int(_get_env("CLASSIFIER_MIN_TEXT_LEN", "50") or "50")
        self.TEXT_TRUNCATE_LIMIT = int(_get_env("CLASSIFIER_TEXT_TRUNCATE_LIMIT", "4000") or "4000")

        # Types/topics configuration (two strings in config)
        default_types = (
            "advertising,sponsored,announcement,sales,poll,digest,news,event,fact,results,"
            "expert opinion,analysis,story,other"
        )
        default_topics = (
            "economics,politics,finance,Technology and Science,Culture and Arts,Health and Sports,"
            "Society and History,Automotive and Transport,Real Estate and Construction,business and entrepreneurship,other"
        )
        self.TYPE_LIST_STR = _get_env("CLASSIFIER_TYPES", default_types) or default_types
        self.TOPIC_LIST_STR = _get_env("CLASSIFIER_TOPICS", default_topics) or default_topics

        def _split_list(s: str) -> List[str]:
            return [x.strip() for x in (s or "").split(",") if x.strip()]

        self.TYPE_LIST: List[str] = _split_list(self.TYPE_LIST_STR)
        self.TOPIC_LIST: List[str] = _split_list(self.TOPIC_LIST_STR)


settings = Settings()