import asyncio
import logging
import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Подхватим .env из корня проекта при локальном запуске
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_PATH = os.path.join(BASE_DIR, ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

from .config import settings
from .storage import ensure_dirs
from .telegram_client import TelegramMonitor


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
)
logger = logging.getLogger("collector.main")

app = FastAPI(title="MediaGenerator Collector", version="0.1.0")

monitor = TelegramMonitor()
startup_task = None


@app.on_event("startup")
async def on_startup():
    ensure_dirs(settings.DATA_DIR, settings.PENDING_DIR, settings.APPROVED_DIR, settings.SESSIONS_DIR)
    # Стартуем мониторинг
    await monitor.start()


@app.on_event("shutdown")
async def on_shutdown():
    await monitor.stop()


@app.get("/health")
async def health():
    status = "ok" if monitor.authorized else "unauthorized"
    return JSONResponse({
        "service": "collector",
        "status": status,
        "authorized": monitor.authorized,
        "channels": settings.MONITORING_CHANNELS,
        "data_dirs": {
            "data": settings.DATA_DIR,
            "pending": settings.PENDING_DIR,
            "approved": settings.APPROVED_DIR,
            "sessions": settings.SESSIONS_DIR,
        }
    })