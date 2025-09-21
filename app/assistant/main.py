import logging
import os
import json
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

# Подхватим .env из корня проекта при локальном запуске
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_PATH = os.path.join(BASE_DIR, ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

from .config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("assistant.main")

app = FastAPI(title="MediaGenerator Assistant", version="0.2.0")


@app.on_event("startup")
async def on_startup():
    # Убедимся, что директории существуют
    os.makedirs(settings.PENDING_DIR, exist_ok=True)
    os.makedirs(settings.APPROVED_DIR, exist_ok=True)
    logger.info("Assistant service started (webhook mode)")


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


# --- Вспомогательные функции ---

def _tg_timeout() -> int:
    # Короткие запросы к Bot API
    return 30


def _tg_api(method: str, body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/{method}"
    try:
        req = urlrequest.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urlrequest.urlopen(req, timeout=_tg_timeout()) as resp:
            text = resp.read().decode("utf-8")
            data = json.loads(text)
            if isinstance(data, dict) and not data.get("ok", True):
                logger.warning(f"Bot API not ok: method={method}, resp={data}")
            return data
    except HTTPError as he:
        try:
            err_body = he.read().decode("utf-8")
        except Exception:
            err_body = str(he)
        logger.error(f"HTTPError {he.code} on {url}: {err_body}")
    except URLError as ue:
        logger.error(f"URLError on {url}: {ue}")
    except Exception:
        logger.exception(f"Request failed: {url}")
    return None


def _answer_callback(callback_id: Optional[str], text: str) -> None:
    if not callback_id:
        return
    _tg_api("answerCallbackQuery", {
        "callback_query_id": callback_id,
        "text": text,
        "show_alert": False
    })


def _delete_message(chat_id: Optional[int], message_id: Optional[int]) -> None:
    if not chat_id or not message_id:
        return
    _tg_api("deleteMessage", {"chat_id": chat_id, "message_id": message_id})


def _clear_markup(chat_id: Optional[int], message_id: Optional[int]) -> None:
    if not chat_id or not message_id:
        return
    _tg_api("editMessageReplyMarkup", {
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": {"inline_keyboard": []}
    })


def _approve(filename: str) -> bool:
    src = os.path.join(settings.PENDING_DIR, filename)
    dst = os.path.join(settings.APPROVED_DIR, filename)
    try:
        if not os.path.isfile(src):
            logger.warning(f"Approve requested but file not found: {src}")
            return False
        os.replace(src, dst)
        logger.info(f"Approved and moved: {src} -> {dst}")
        return True
    except Exception:
        logger.exception(f"Approve failed for {filename}")
        return False


def _reject(filename: str) -> bool:
    src = os.path.join(settings.PENDING_DIR, filename)
    try:
        if not os.path.isfile(src):
            logger.warning(f"Reject requested but file not found: {src}")
            return False
        os.remove(src)
        logger.info(f"Rejected and removed: {src}")
        return True
    except Exception:
        logger.exception(f"Reject failed for {filename}")
        return False


# --- Webhook endpoint ---
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    try:
        upd = await request.json()
    except Exception:
        logger.exception("Invalid JSON in webhook request")
        return JSONResponse({"ok": True})

    cbq = upd.get("callback_query")
    if not cbq:
        # Нас интересуют только callback_query; остальное игнорируем молча
        return JSONResponse({"ok": True})

    data = (cbq.get("data") or "").strip()
    message = cbq.get("message") or {}
    chat_id = ((message.get("chat") or {}).get("id"))
    msg_id = message.get("message_id")
    cb_id = cbq.get("id")

    logger.info(f"Callback received: data={data}, chat_id={chat_id}, message_id={msg_id}")

    result_text = ""
    if data.startswith("approve:"):
        filename = os.path.basename(data.split(":", 1)[1])
        ok = _approve(filename)
        result_text = "✅ Одобрено" if ok else "Не найден файл"
    elif data.startswith("reject:"):
        filename = os.path.basename(data.split(":", 1)[1])
        ok = _reject(filename)
        result_text = "❌ Отклонено" if ok else "Не найден файл"
    else:
        result_text = "Неверная команда"

    # Ответим нажатию
    _answer_callback(cb_id, result_text)

    # По требованию: удаляем сообщение после нажатия
    _delete_message(chat_id, msg_id)
    # На случай отсутствия прав на удаление — уберём клавиатуру
    _clear_markup(chat_id, msg_id)

    return JSONResponse({"ok": True})