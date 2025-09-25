import logging
import os
from typing import Optional, Dict, Any

from fastapi import FastAPI, Body
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_PATH = os.path.join(BASE_DIR, ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

from .config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("classifier.main")

app = FastAPI(title="MediaGenerator Classifier", version="0.1.0")


@app.on_event("startup")
async def on_startup():
    try:
        logger.info("Classifier version: %s", getattr(app, "version", "unknown"))
    except Exception:
        pass
    logger.info("Classifier service started")

@app.get("/health")
async def health():
    return JSONResponse({
        "ok": True,
        "status": "ok",
        "service": "classifier",
        "use_heuristics": settings.USE_HEURISTICS,
        "keywords_count": len(settings.KEYWORDS),
    })

# Added readiness probe to comply with service standards
@app.get("/ready")
async def ready():
    return JSONResponse({
        "ok": True,
        "ready": True,
        "service": "classifier",
    })

@app.post("/api/classifier/classify")
async def classify(payload: Dict[str, Any] = Body(...)):
    text = (payload.get("text") or "")
    title = (payload.get("title") or "")
    source = (payload.get("source") or None)
    # Simple heuristic classification
    def _score(t: str) -> int:
        lower = t.lower()
        return sum(1 for w in settings.KEYWORDS if w in lower)
    score = _score(text) + _score(title)
    is_news = (score >= 1 and (len(text.strip()) + len(title.strip())) >= settings.MIN_TEXT_LEN)
    suggested_action = "review"
    if is_news:
        suggested_action = "approve"
    else:
        suggested_action = "reject"
    return {
        "ok": True,
        "is_news": is_news,
        "topics": [],
        "confidence": 0.6 if is_news else 0.4,
        "suggested_action": suggested_action,
        "source": source,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)