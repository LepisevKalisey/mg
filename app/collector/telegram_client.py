import asyncio
import logging
import os
import json
from typing import Any, Dict, Optional, List, Tuple
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError

from telethon import TelegramClient, events
from telethon.tl.types import Message, MessageMediaPhoto, MessageMediaDocument
from telethon.tl.types import (
    MessageEntityBold,
    MessageEntityItalic,
    MessageEntityUnderline,
    MessageEntityStrike,
    MessageEntityCode,
    MessageEntityPre,
    MessageEntityTextUrl,
    MessageEntityUrl,
    MessageEntityMention,
    MessageEntityHashtag,
    MessageEntityCashtag,
    MessageEntityBotCommand,
    MessageEntityEmail,
    MessageEntityPhone,
    MessageEntitySpoiler,
    MessageEntityBlockquote,
)

from .config import settings
from .storage import save_pending_message


logger = logging.getLogger("collector.telegram")


class TelegramMonitor:
    def __init__(self) -> None:
        session_path = os.path.join(settings.SESSIONS_DIR, "mtproto")
        # Гарантируем наличие директории для файла сессии до инициализации TelegramClient
        os.makedirs(settings.SESSIONS_DIR, exist_ok=True)
        
        # Проверка возможности записи в директорию/файл сессии — частая причина sqlite3 readonly database
        try:
            _test_path = os.path.join(settings.SESSIONS_DIR, ".writetest")
            with open(_test_path, "w", encoding="utf-8") as _f:
                _f.write("ok")
            os.remove(_test_path)
        except Exception as e:
            logger.error(
                "Sessions dir '%s' is not writable: %s. This will cause sqlite3 'readonly database'. "
                "Ensure Docker volume is mounted read-write and permissions/ownership are correct.",
                settings.SESSIONS_DIR, e
            )
        _sess_file = session_path + ".session"
        if os.path.exists(_sess_file) and not os.access(_sess_file, os.W_OK):
            logger.error(
                "Session file '%s' is not writable. Fix permissions or remount volume. ",
                _sess_file
            )

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
        try:
            await self.client.connect()
        except Exception as e:
            logger.exception("Failed to connect Telegram client: %s", e)
            if "readonly" in str(e).lower():
                logger.error(
                    "Likely cause: session SQLite is read-only. Check mount mode and permissions for '%s'",
                    settings.SESSIONS_DIR,
                )
            return
        self._authorized = await self.client.is_user_authorized()
        if not self._authorized:
            logger.error("Telethon is not authorized. Ensure mtproto.session exists in %s and matches API_ID/API_HASH.", settings.SESSIONS_DIR)
            return

        # Регистрируем обработчик событий только если есть список каналов
        chats_filter = self._resolve_chats_filter()
        if not chats_filter:
            logger.warning("Channels list is empty. Skipping event handler registration.")
            return
        self.client.add_event_handler(self._on_new_message, events.NewMessage(chats=chats_filter))
        # Отдельный обработчик альбомов (media group) — будет вызван единоразово на всю группу
        self.client.add_event_handler(self._on_new_album, events.Album(chats=chats_filter))

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
            # Если это часть альбома (media group), обработаем в _on_new_album и здесь игнорируем
            if getattr(msg, "grouped_id", None):
                return

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

            # Отправим уведомление редакторам с кнопками (только текст, с сохранением форматирования)
            await self._send_to_editors(payload, path, source_message=msg)

        except Exception as e:
            logger.exception(f"Failed to process message: {e}")

    async def _on_new_album(self, event: events.Album.Event) -> None:
        """Обрабатываем альбом (media group) как единый пост: пересылаем только текстовую часть (капшен),
        сохраняя форматирование, без дублирования по каждому медиа."""
        try:
            msgs: List[Message] = list(event.messages) if hasattr(event, "messages") else []
            if not msgs:
                return

            # Берем чат (канал)
            chat = await event.get_chat()
            channel_id = getattr(chat, "id", None)
            channel_username = getattr(chat, "username", None)
            channel_title = getattr(chat, "title", None) or channel_username or "unknown"

            # Выберем "основное" сообщение для текста (обычно в одном из элементов альбома есть caption)
            primary = None
            non_empty = [m for m in msgs if (m.message or "").strip()]
            if non_empty:
                primary = max(non_empty, key=lambda m: len(m.message))
            else:
                primary = msgs[0]

            msg = primary

            # Метаданные для сохранения
            views = getattr(msg, "views", None)
            forwards = getattr(msg, "forwards", None)
            reactions = None
            if getattr(msg, "reactions", None):
                try:
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
                "media": None,  # альбом не пересылаем, сохраняем только текст
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
            logger.info(f"Saved pending album message: {path}")

            await self._send_to_editors(payload, path, source_message=msg)

        except Exception as e:
            logger.exception(f"Failed to process album: {e}")

    # ---- Formatting helpers ----
    @staticmethod
    def _utf16_len(s: str) -> int:
        # Считаем длину строки в UTF-16 code units (как требует Bot API для offsets)
        total = 0
        for ch in s or "":
            o = ord(ch)
            total += 2 if o > 0xFFFF else 1
        return total

    def _map_entity(self, ent: Any) -> Optional[Dict[str, Any]]:
        # Маппинг Telethon entity -> Bot API entity
        if isinstance(ent, MessageEntityBold):
            return {"type": "bold", "offset": ent.offset, "length": ent.length}
        if isinstance(ent, MessageEntityItalic):
            return {"type": "italic", "offset": ent.offset, "length": ent.length}
        if isinstance(ent, MessageEntityUnderline):
            return {"type": "underline", "offset": ent.offset, "length": ent.length}
        if isinstance(ent, MessageEntityStrike):
            return {"type": "strikethrough", "offset": ent.offset, "length": ent.length}
        if isinstance(ent, MessageEntityCode):
            return {"type": "code", "offset": ent.offset, "length": ent.length}
        if isinstance(ent, MessageEntityPre):
            d = {"type": "pre", "offset": ent.offset, "length": ent.length}
            lang = getattr(ent, "language", None)
            if lang:
                d["language"] = lang
            return d
        if isinstance(ent, MessageEntityTextUrl):
            return {"type": "text_link", "offset": ent.offset, "length": ent.length, "url": ent.url}
        if isinstance(ent, MessageEntityUrl):
            return {"type": "url", "offset": ent.offset, "length": ent.length}
        if isinstance(ent, MessageEntityMention):
            return {"type": "mention", "offset": ent.offset, "length": ent.length}
        if isinstance(ent, MessageEntityHashtag):
            return {"type": "hashtag", "offset": ent.offset, "length": ent.length}
        if isinstance(ent, MessageEntityCashtag):
            return {"type": "cashtag", "offset": ent.offset, "length": ent.length}
        if isinstance(ent, MessageEntityBotCommand):
            return {"type": "bot_command", "offset": ent.offset, "length": ent.length}
        if isinstance(ent, MessageEntityEmail):
            return {"type": "email", "offset": ent.offset, "length": ent.length}
        if isinstance(ent, MessageEntityPhone):
            return {"type": "phone_number", "offset": ent.offset, "length": ent.length}
        if isinstance(ent, MessageEntitySpoiler):
            return {"type": "spoiler", "offset": ent.offset, "length": ent.length}
        if isinstance(ent, MessageEntityBlockquote):
            return {"type": "blockquote", "offset": ent.offset, "length": ent.length}
        # Прочие не маппим
        return None

    def _extract_text_and_entities(self, msg: Message) -> Tuple[str, List[Dict[str, Any]]]:
        text = msg.message or ""
        entities = getattr(msg, "entities", None) or []
        bot_entities: List[Dict[str, Any]] = []
        for ent in entities:
            mapped = self._map_entity(ent)
            if mapped:
                bot_entities.append(mapped)
        return text, bot_entities

    def _compose_title_and_text(self, payload: Dict[str, Any], text: str, entities: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
        title = payload.get("channel_title") or payload.get("channel_name") or "Канал"
        username = payload.get("channel_username")
        msg_id = payload.get("message_id")
        post_url = f"https://t.me/{username}/{msg_id}" if username else None

        # Базовая строка — название канала (как ссылка, если возможно)
        full_text = title
        out_entities: List[Dict[str, Any]] = []
        title_utf16 = self._utf16_len(title)
        if post_url:
            out_entities.append({
                "type": "text_link",
                "offset": 0,
                "length": title_utf16,
                "url": post_url,
            })

        if text:
            # Добавим пустую строку и сам текст
            prefix = f"{title}\n\n"
            full_text = prefix + text
            shift = self._utf16_len(prefix)
            for e in entities:
                e2 = dict(e)
                e2["offset"] = e2["offset"] + shift
                out_entities.append(e2)
        else:
            # Только заголовок
            full_text = title if not username else title  # уже учли ссылку через entity выше

        return full_text, out_entities

    def _build_editor_text(self, payload: Dict[str, Any]) -> str:
        # Больше не используется для отправки, но оставляем для совместимости вызовов, если где-то останется
        title = payload.get("channel_title") or payload.get("channel_name") or "Канал"
        username = payload.get("channel_username")
        msg_id = payload.get("message_id")
        url = None
        if username:
            url = f"https://t.me/{username}/{msg_id}"
        text = payload.get("text") or (payload.get("media") or {}).get("caption") or "(без текста)"
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

    async def _send_to_editors(self, payload: Dict[str, Any], saved_path: str, *, source_message: Optional[Message] = None, text_override: Optional[str] = None, entities_override: Optional[List[Dict[str, Any]]] = None) -> None:
        if not settings.BOT_TOKEN or not settings.EDITORS_CHANNEL_ID:
            logger.warning("BOT_TOKEN or EDITORS_CHANNEL_ID not configured. Skipping send to editors.")
            return

        # Исходный текст и entities из сообщения (или переданные явно)
        if text_override is not None and entities_override is not None:
            src_text, src_entities = text_override, entities_override
        elif source_message is not None:
            src_text, src_entities = self._extract_text_and_entities(source_message)
        else:
            src_text, src_entities = payload.get("text") or "", []

        # Собираем итоговый текст: "<title-as-link>\n\n<text-with-formatting>"
        final_text, final_entities = self._compose_title_and_text(payload, src_text, src_entities)

        # Подготовим кнопки
        file_name = os.path.basename(saved_path)
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
            "text": final_text,
            "entities": final_entities,
            "disable_web_page_preview": True,
            "reply_markup": reply_markup,
        }

        api_url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"

        def _post_json(url: str, data: Dict[str, Any]) -> None:
            try:
                req = urlrequest.Request(url, data=json.dumps(data, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"})
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