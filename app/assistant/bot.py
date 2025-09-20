import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from .config import settings

logger = logging.getLogger("assistant.bot")


class TelegramAssistantBot:
    def __init__(self) -> None:
        if not settings.BOT_TOKEN:
            raise RuntimeError("BOT_TOKEN is required for Assistant")
        self._base = f"https://api.telegram.org/bot{settings.BOT_TOKEN}"
        self._offset: Optional[int] = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        logger.info("Assistant bot started (long-poll)")
        # Убедимся, что webhook снят, иначе getUpdates не будет работать
        await self._ensure_long_poll_mode()
        while self._running:
            try:
                updates = await self._get_updates(timeout=settings.POLL_TIMEOUT)
                if updates:
                    for update in updates:
                        await self._handle_update(update)
                else:
                    await asyncio.sleep(settings.POLL_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Polling loop error")
                await asyncio.sleep(1)

    async def stop(self) -> None:
        self._running = False

    async def _get_updates(self, timeout: int) -> list[dict]:
        params = {"timeout": timeout}
        if self._offset is not None:
            params["offset"] = self._offset
        url = f"{self._base}/getUpdates"
        data = await asyncio.to_thread(self._post_json, url, params)
        if not data:
            return []
        if not data.get("ok"):
            logger.warning(f"getUpdates not ok: {data}")
            return []
        result = data.get("result", [])
        if result:
            self._offset = result[-1]["update_id"] + 1
        return result

    async def _ensure_long_poll_mode(self) -> None:
        try:
            # Снимем webhook, если он был установлен ранее
            url = f"{self._base}/deleteWebhook"
            body = {"drop_pending_updates": False}
            resp = await asyncio.to_thread(self._post_json, url, body)
            logger.info(f"deleteWebhook resp: {resp}")
        except Exception:
            logger.exception("Failed to delete webhook")

    def _post_json(self, url: str, body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            req = urlrequest.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
            with urlrequest.urlopen(req, timeout=timeout_guard(url)) as resp:
                text = resp.read().decode("utf-8")
                data = json.loads(text)
                if isinstance(data, dict) and not data.get("ok", True):
                    logger.warning(f"Bot API not ok: url={url}, resp={data}")
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

    async def _handle_update(self, upd: Dict[str, Any]) -> None:
        cbq = upd.get("callback_query")
        if not cbq:
            return
        data = cbq.get("data") or ""
        message = cbq.get("message") or {}
        chat_id = ((message.get("chat") or {}).get("id"))
        msg_id = message.get("message_id")
        logger.info(f"Callback received: data={data}, chat_id={chat_id}, message_id={msg_id}")
        
        if data.startswith("approve:"):
            filename = data.split(":", 1)[1]
            safe_name = os.path.basename(filename)
            ok = await self._approve(safe_name)
            await self._answer_callback(cbq.get("id"), "✅ Одобрено" if ok else "Не найден файл")
            if chat_id and msg_id:
                # По требованию: удаляем сообщение с кнопками после любого нажатия
                await self._delete_message(chat_id, msg_id)
                # На случай отсутствия прав на удаление — уберём клавиатуру
                await self._edit_markup(chat_id, msg_id)
        elif data.startswith("reject:"):
            filename = data.split(":", 1)[1]
            safe_name = os.path.basename(filename)
            ok = await self._reject(safe_name)
            await self._answer_callback(cbq.get("id"), "❌ Отклонено" if ok else "Не найден файл")
            if chat_id and msg_id:
                # По требованию: удаляем сообщение с кнопками после любого нажатия
                await self._delete_message(chat_id, msg_id)
                # На случай отсутствия прав на удаление — уберём клавиатуру
                await self._edit_markup(chat_id, msg_id)

    async def _approve(self, filename: str) -> bool:
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

    async def _reject(self, filename: str) -> bool:
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

    async def _answer_callback(self, callback_id: Optional[str], text: str) -> None:
        if not callback_id:
            return
        url = f"{self._base}/answerCallbackQuery"
        body = {"callback_query_id": callback_id, "text": text, "show_alert": False}
        await asyncio.to_thread(self._post_json, url, body)

    async def _edit_markup(self, chat_id: int, message_id: int) -> None:
        url = f"{self._base}/editMessageReplyMarkup"
        # Убираем inline-клавиатуру
        body = {"chat_id": chat_id, "message_id": message_id, "reply_markup": {"inline_keyboard": []}}
        await asyncio.to_thread(self._post_json, url, body)
    
    # no return here

    async def _delete_message(self, chat_id: int, message_id: int) -> None:
        url = f"{self._base}/deleteMessage"
        body = {"chat_id": chat_id, "message_id": message_id}
        await asyncio.to_thread(self._post_json, url, body)


def timeout_guard(url: str) -> int:
    # Для long-poll getUpdates используем таймаут с запасом поверх POLL_TIMEOUT
    try:
        from .config import settings as _settings
        if "getUpdates" in url:
            # запас, чтобы не ронять long-poll по сокетному таймауту
            return int(_settings.POLL_TIMEOUT) + 15
    except Exception:
        pass
    # дефолтный таймаут для коротких запросов (answerCallback, editMessageReplyMarkup)
    return 30