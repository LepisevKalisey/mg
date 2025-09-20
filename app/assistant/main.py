import asyncio
import logging
import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Подхватим .env
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_PATH = os.path.join(BASE_DIR, ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

from .config import settings
from .bot import TelegramAssistantBot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("assistant.main")

app = FastAPI(title="MediaGenerator Assistant", version="0.1.0")

bot = TelegramAssistantBot()
_task: asyncio.Task | None = None


@app.on_event("startup")
async def on_startup():
    # Проверим наличие директорий
    os.makedirs(settings.PENDING_DIR, exist_ok=True)
    os.makedirs(settings.APPROVED_DIR, exist_ok=True)
    global _task
    _task = asyncio.create_task(bot.start())


@app.on_event("shutdown")
async def on_shutdown():
    await bot.stop()
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass


@app.get("/health")
async def health():
    return JSONResponse({
        "service": "assistant",
        "status": "ok",
        "data_dirs": {
            "pending": settings.PENDING_DIR,
            "approved": settings.APPROVED_DIR,
        }
    })