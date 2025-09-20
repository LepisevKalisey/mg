import asyncio
import logging
import os
import json
from typing import Any, Dict, Optional, List
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError

from telethon import TelegramClient, events
from telethon.tl.types import Message, MessageMediaPhoto, MessageMediaDocument

from .config import settings
from .storage import save_pending_message


logger = logging.getLogger("collector.telegram")


class TelegramMonitor:
    def __init__(self) -> None:
        session_path = os.path.join(settings.SESSIONS_DIR, "mtproto")
        # Для user-сессии используем сохранённый файл сессии
        self.client = TelegramClient(
            session=session_path,
            api_id=settings.API_ID,
            api_hash=settings.API_HASH
        )

        self._task: Optional[asyncio.Task] = None
        self._started = False
        self._authorized = False

    @property
    def authorized(self) -> bool:
        return self._authorized

    async def start(self) -> None:
        await self.client.connect()
        self._authorized = await self.client.is_user_authorized()
        if not self._authorized:
            logger.error("Telethon is not authorized. Run interactive auth first (app/collector/auth_login.py) with PHONE or PHONE_NUMBER in .env.")
            return

        # Регистрируем обработчик событий только если есть список каналов
        chats_filter = self._resolve_chats_filter()
        if not chats_filter:
            logger.warning("Channels list is empty. Skipping event handler registration.")
            return
        self.client.add_event_handler(self._on_new_message, events.NewMessage(chats=chats_filter))

        # Запускаем run_until_disconnected в фоне
        self._task = asyncio.create_task(self._run_client())
        self._started = True
        logger.info("Telegram monitoring started")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if self.client.is_connected():
            await self.client.disconnect()

        self._started = False
        logger.info("Telegram monitoring stopped")

    async def _run_client(self) -> None:
        try:
            await self.client.run_until_disconnected()
        except asyncio.CancelledError:
            pass

    def _resolve_chats_filter(self) -> List[str] | None:
        # Возвращаем список чатов/каналов (@channel)
        if not settings.MONITORING_CHANNELS:
            logger.warning("No channels configured. Set MONITORING_CHANNELS or CHANNELS_FILE")
            return None
        return settings.MONITORING_CHANNELS

    async def _on_new_message(self, event: events.NewMessage.Event) -> None:
        try:
            msg: Message = event.message

            # Берем чат (канал)
            chat = await event.get_chat()
            channel_id = getattr(chat, "id", None)
            channel_username = getattr(chat, "username", None)
            channel_title = getattr(chat, "title", None) or channel_username or "unknown"

            media_type = None
            caption = None
            if msg.media:
                if isinstance(msg.media, MessageMediaPhoto):
                    media_type = "photo"
                elif isinstance(msg.media, MessageMediaDocument):
                    media_type = "document"
                else:
                    media_type = "unknown"
                caption = msg.message

            # Метаданные
            views = getattr(msg, "views", None)
            forwards = getattr(msg, "forwards", None)
            reactions = None
            if getattr(msg, "reactions", None):
                try:
                    # Сериализуем реакции как список {emoji, count}
                    reactions = [
                        {"emoji": getattr(c.reaction, "emoticon", None), "count": c.count}
                        for c in msg.reactions.results
                    ]
                except Exception:
                    reactions = None

            author = {}
            if msg.sender:
                sender = await msg.get_sender()
                author = {
                    "id": getattr(sender, "id", None),
                    "username": getattr(sender, "username", None),
                    "first_name": getattr(sender, "first_name", None),
                    "last_name": getattr(sender, "last_name", None),
                }

            payload: Dict[str, Any] = {
                "id": f"{channel_id}_{msg.id}",
                "channel_id": str(channel_id),
                "channel_name": str(channel_title),
                "channel_username": channel_username,
                "channel_title": channel_title,
                "message_id": msg.id,
                "text": msg.message,
                "media": {
                    "type": media_type,
                    "file_id": None,
                    "caption": caption,
                } if media_type else None,
                "author": author,
                "timestamp": msg.date.isoformat() if msg.date else None,
                "metadata": {
                    "views": views,
                    "forwards": forwards,
                    "reactions": reactions,
                },
                "status": "pending",
                "moderation": None,
            }

            path = save_pending_message(settings.PENDING_DIR, payload)
            logger.info(f"Saved pending message: {path}")

            # Отправим уведомление редакторам с кнопками
            await self._send_to_editors(payload, path)

        except Exception as e:
            logger.exception(f"Failed to process message: {e}")

    def _build_editor_text(self, payload: Dict[str, Any]) -> str:
        title = payload.get("channel_title") or payload.get("channel_name") or "Канал"
        username = payload.get("channel_username")
        msg_id = payload.get("message_id")
        url = None
        if username:
            url = f"https://t.me/{username}/{msg_id}"
        text = payload.get("text") or (payload.get("media") or {}).get("caption") or "(без текста)"
        # Ограничим длину
        excerpt = (text[:900] + "…") if len(text) > 900 else text

        parts = [f"<b>Новый пост</b>", f"Канал: {('@'+username) if username else title}"]
        if url:
            parts.append(f"Ссылка: <a href=\"{url}\">открыть в Telegram</a>")
        parts.append("")
        parts.append(self._escape_html(excerpt))
        return "\n".join(parts)

    @staticmethod
    def _escape_html(text: str) -> str:
        return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    async def _send_to_editors(self, payload: Dict[str, Any], saved_path: str) -> None:
        if not settings.BOT_TOKEN or not settings.EDITORS_CHANNEL_ID:
            logger.warning("BOT_TOKEN or EDITORS_CHANNEL_ID not configured. Skipping send to editors.")
            return

        # Подготовим сообщение и кнопки
        file_name = os.path.basename(saved_path)
        text = self._build_editor_text(payload)
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ Ok", "callback_data": f"approve:{file_name}"},
                    {"text": "❌ Отмена", "callback_data": f"reject:{file_name}"},
                ]
            ]
        }

        body = {
            "chat_id": settings.EDITORS_CHANNEL_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": reply_markup,
        }

        api_url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"

        def _post_json(url: str, data: Dict[str, Any]) -> None:
            try:
                req = urlrequest.Request(url, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"})
                with urlrequest.urlopen(req, timeout=10) as resp:
                    if resp.status != 200:
                        logger.warning(f"Bot API non-200 response: {resp.status}")
            except HTTPError as he:
                try:
                    err_body = he.read().decode("utf-8")
                except Exception:
                    err_body = str(he)
                logger.error(f"Bot API HTTPError: {he.code} {err_body}")
            except URLError as ue:
                logger.error(f"Bot API URLError: {ue}")
            except Exception as e:
                logger.exception(f"Bot API request failed: {e}")

        # Не блокируем event loop
        await asyncio.to_thread(_post_json, api_url, body)