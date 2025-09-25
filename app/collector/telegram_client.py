import asyncio
import logging
import os
import json
import re
from typing import Any, Dict, Optional, List, Tuple
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError
from collections import deque

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
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

from .config import settings
from .storage import save_pending_message, save_approved_message


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

        # Храним EventBuilder-ы для возможности динамического обновления фильтров
        self._eh_new_msg_builder: Optional[events.NewMessage] = None
        self._eh_album_builder: Optional[events.Album] = None

        # Тихие часы: ручной флаг и опциональное расписание (строка вида "22:00-08:00")
        self._quiet_mode: bool = False
        self._quiet_schedule: Optional[str] = None

        # Состояние авторизации (через код/пароль)
        self._auth_phone: Optional[str] = None
        self._auth_hash: Optional[str] = None
        self._await_code: bool = False
        self._await_password: bool = False
        self._auth_chat_id: Optional[int] = None

        # De-duplication of processed posts (channel_id + message_id)
        self._recent_keys: deque[str] = deque()
        self._recent_set: set[str] = set()
        self._recent_max: int = 1000

        # Простая фильтрация рекламных/партнёрских постов
        self._ad_filter_enabled: bool = settings.AD_FILTER_ENABLED
        _default_words = [
            "реклама", "реклам", "спонсор", "спонсировано", "партнер", "партнёр",
            "партнерский", "партнёрский", "партнерская", "партнёрская",
            "промокод", "скидка", "sale", "подпишись", "подписывайтесь", "поддержите",
            "спецпредложение", "sponsored", "advertisement", "ad:", "#ad", "#реклама",
            "promo code", "use code", "affiliate", "реферальн", "переходите по ссылке",
        ]
        words = settings.AD_FILTER_WORDS if settings.AD_FILTER_WORDS else _default_words
        self._ad_filter_words: List[str] = [w.lower() for w in words]

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
            # Уведомим через бота, что требуется авторизация
            await self.notify_auth_required()
            return
        self._authorized = await self.client.is_user_authorized()
        if not self._authorized:
            logger.error("Telethon is not authorized. Ensure mtproto.session exists in %s and matches API_ID/API_HASH.", settings.SESSIONS_DIR)
            # Уведомим через бота, что требуется авторизация
            await self.notify_auth_required()
            return

        # Регистрируем обработчик событий только если есть список каналов
        chats_filter = self._resolve_chats_filter()
        if not chats_filter:
            logger.warning("Channels list is empty. Skipping event handler registration.")
            return
        # Вместо прямой регистрации используем refresh_handlers, чтобы избежать дубликатов
        await self.refresh_handlers(chats_filter)

        # Запускаем run_until_disconnected в фоне
        self._task = asyncio.create_task(self._run_client())
        self._started = True
        logger.info("Telegram monitoring started")

    def _post_auth_start_handlers(self) -> None:
        """После успешной авторизации регистрируем обработчики и запускаем фонового клиента."""
        try:
            chats_filter = self._resolve_chats_filter()
            if chats_filter:
                try:
                    # Перерегистрируем обработчики асинхронно, чтобы избежать двойной регистрации
                    asyncio.create_task(self.refresh_handlers(chats_filter))
                except Exception:
                    logger.exception("Failed to register handlers after auth")
            if not self._task or self._task.done():
                self._task = asyncio.create_task(self._run_client())
                self._started = True
                logger.info("Telegram client run loop started after auth")
        except Exception:
            logger.exception("_post_auth_start_handlers failed")

    def _resolve_chats_filter(self) -> List[str] | None:
        # Возвращаем нормализованный список чатов/каналов (@channel)
        if not settings.MONITORING_CHANNELS:
            logger.warning("No channels configured. Set MONITORING_CHANNELS or CHANNELS_FILE")
            return None
        return self._normalize_channels(settings.MONITORING_CHANNELS)

    def _normalize_channels(self, channels: List[str]) -> List[str]:
        """Нормализуем список каналов: убираем пустые/дубликаты, хвостовые запятые,
        конвертируем t.me ссылки в @username."""
        normalized: List[str] = []
        seen = set()
        for ch in channels:
            s = (ch or "").strip()
            if not s:
                continue
            s = s.rstrip(",;.")
            if s.startswith("https://t.me/") or s.startswith("http://t.me/"):
                tail = s.split("/", 3)[-1].split("?")[0]
                if tail:
                    if tail.startswith("+"):
                        # Инвайт-ссылки нельзя использовать в фильтре событий
                        continue
                    s = f"@{tail}"
            elif not s.startswith("@"):
                s = f"@{s}"
            if s not in seen:
                normalized.append(s)
                seen.add(s)
        return normalized

    async def _run_client(self) -> None:
        """Фоновый запуск клиента до отключения."""
        try:
            if not self.client.is_connected():
                await self.client.connect()
            await self.client.run_until_disconnected()
        except asyncio.CancelledError:
            logger.info("Telegram client run loop cancelled")
            raise
        except Exception as e:
            logger.exception("Telegram client run loop error: %s", e)
        finally:
            self._started = False
            logger.info("Telegram client run loop stopped")

    async def refresh_handlers(self, channels: List[str]) -> None:
        """Пере-регистрируем event handlers под новый список каналов без рестарта."""
        try:
            # Снимем старые обработчики
            if self._eh_new_msg_builder is not None:
                try:
                    self.client.remove_event_handler(self._on_new_message, self._eh_new_msg_builder)
                except Exception:
                    pass
                self._eh_new_msg_builder = None
            if self._eh_album_builder is not None:
                try:
                    self.client.remove_event_handler(self._on_new_album, self._eh_album_builder)
                except Exception:
                    pass
                self._eh_album_builder = None

            if not channels:
                logger.warning("Channels list is empty. Event handlers are not registered.")
                return

            # Регистрируем новые обработчики
            nm_builder = events.NewMessage(chats=channels)
            al_builder = events.Album(chats=channels)
            self.client.add_event_handler(self._on_new_message, nm_builder)
            self.client.add_event_handler(self._on_new_album, al_builder)
            self._eh_new_msg_builder = nm_builder
            self._eh_album_builder = al_builder
            logger.info("Event handlers registered for channels: %s", ", ".join(map(str, channels)))
        except Exception:
            logger.exception("Failed to refresh event handlers")

    async def set_channels(self, channels: List[str]) -> None:
        """Обновить список каналов в памяти и обработчики. Файл конфигурации обновляется извне."""
        # Убираем дубликаты и пустые
        normalized = []
        seen = set()
        for ch in channels:
            ch = (ch or '').strip()
            if not ch:
                continue
            if ch not in seen:
                normalized.append(ch)
                seen.add(ch)
        settings.MONITORING_CHANNELS = normalized
        if self._authorized:
            await self.refresh_handlers(normalized)

    async def join_channel(self, identifier: str) -> bool:
        """Подписаться на канал/чат по @username или ссылке t.me/.. или инвайт-ссылке (+hash)."""
        if not self._authorized:
            logger.error("Cannot join channel: client not authorized")
            return False
        ident = (identifier or '').strip()
        if not ident:
            return False
        try:
            # t.me/ links handling
            if ident.startswith('https://t.me/') or ident.startswith('http://t.me/'):
                tail = ident.split('/', 3)[-1]
                # Invite links like https://t.me/+abcdef
                if tail.startswith('+'):
                    invite_hash = tail[1:]
                    await self.client(ImportChatInviteRequest(invite_hash))
                    return True
                # public username
                username = tail.split('?')[0]
                if username:
                    if username.startswith('+'):
                        # rare case: t.me/+hash (already handled above), fallthrough
                        invite_hash = username[1:]
                        await self.client(ImportChatInviteRequest(invite_hash))
                        return True
                    ent = await self.client.get_entity(username)
                    await self.client(JoinChannelRequest(ent))
                    return True
                return False
            # @username
            uname = ident[1:] if ident.startswith('@') else ident
            if uname:
                ent = await self.client.get_entity(uname)
                await self.client(JoinChannelRequest(ent))
                return True
            return False
        except Exception as e:
            logger.warning("Failed to join '%s': %s", identifier, e)
            return False

    async def leave_channel(self, identifier: str) -> bool:
        """Отписаться от канала/чата по @username или ссылке t.me/..."""
        if not self._authorized:
            logger.error("Cannot leave channel: client not authorized")
            return False
        ident = (identifier or '').strip()
        if not ident:
            return False
        try:
            # For t.me invite links, we cannot compute back channel easily; try resolving entity when possible
            if ident.startswith('https://t.me/') or ident.startswith('http://t.me/'):
                tail = ident.split('/', 3)[-1]
                if tail.startswith('+'):
                    # no username available; cannot resolve reliably, ignore
                    return True  # consider no-op
                username = tail.split('?')[0]
                ent = await self.client.get_entity(username)
                await self.client(LeaveChannelRequest(ent))
                return True
            uname = ident[1:] if ident.startswith('@') else ident
            ent = await self.client.get_entity(uname)
            await self.client(LeaveChannelRequest(ent))
            return True
        except Exception as e:
            logger.warning("Failed to leave '%s': %s", identifier, e)
            return False

    def set_quiet_mode(self, on: bool) -> None:
        self._quiet_mode = bool(on)

    def set_quiet_schedule(self, schedule: Optional[str]) -> None:
        # Ожидаем формат HH:MM-HH:MM или None
        self._quiet_schedule = schedule.strip() if schedule else None

    def _is_in_quiet_schedule(self) -> bool:
        if not self._quiet_schedule:
            return False
        try:
            import datetime as _dt
            rng = self._quiet_schedule
            if '-' not in rng:
                return False
            start_s, end_s = [p.strip() for p in rng.split('-', 1)]
            sh, sm = [int(x) for x in start_s.split(':', 1)]
            eh, em = [int(x) for x in end_s.split(':', 1)]
            now = _dt.datetime.now().time()
            start_t = _dt.time(sh, sm)
            end_t = _dt.time(eh, em)
            if start_t <= end_t:
                # обычный интервал в пределах суток
                return start_t <= now <= end_t
            else:
                # интервал через полночь
                return now >= start_t or now <= end_t
        except Exception:
            logger.warning("Invalid quiet schedule format: %s", self._quiet_schedule)
            return False

    def is_quiet_now(self) -> bool:
        return self._quiet_mode or self._is_in_quiet_schedule()

    async def _on_new_album(self, event: events.Album.Event) -> None:
        """Обрабатываем альбом (media group) как единый пост: пересылаем только текстовую часть (капшен),
        сохраняя форматирование, без дублирования по каждому медиа."""
        try:
            msgs: List[Message] = list(event.messages) if hasattr(event, "messages") else []
            # Игнорируем альбомы из одного элемента (во избежание дублей с NewMessage)
            if not msgs or len(msgs) <= 1:
                return

            # Берем чат (канал)
            chat = await event.get_chat()
            channel_id = getattr(chat, "id", None)
            channel_username = getattr(chat, "username", None)
            channel_title = getattr(chat, "title", None) or channel_username or "unknown"

            # De-duplication guard: используем уникальный идентификатор альбома (grouped_id),
            # чтобы не отправлять повторно, если Telethon доставит событие Album несколько раз
            group_id = getattr(msg, "grouped_id", None) or (getattr(msgs[0], "grouped_id", None) if msgs else None)
            if self._is_duplicate_and_mark(channel_id, group_id):
                return

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

            # Extract topics from caption
            topics: List[str] = []
            try:
                t = msg.message or ""
                if t:
                    seen = set()
                    for m in re.finditer(r"(?<!\w)#([\w\d_А-Яа-яЁё]+)", t, flags=re.UNICODE):
                        tag = "#" + m.group(1)
                        if tag not in seen:
                            seen.add(tag)
                            topics.append(tag)
            except Exception:
                topics = []

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
                "topics": topics,
                "status": "pending",
                "moderation": None,
            }

            classification = await self._classify_post(msg.message)
            decision = self._decide_auto_approval(classification)

            if decision.get("auto_approve"):
                payload["status"] = "approved"
                payload["moderation"] = {"classification": classification, "auto_approved": True}
                path = save_approved_message(settings.APPROVED_DIR, payload)
                logger.info(f"Saved approved album message: {path}")
                return
            elif decision.get("send_to_approval"):
                payload["moderation"] = {"classification": classification, "auto_approved": False}
                path = save_pending_message(settings.PENDING_DIR, payload)
                logger.info(f"Saved pending album message: {path}")
                await self._send_to_editors(payload, path, source_message=msg)
                return
            else:
                logger.info("Dropping album %s after classification '%s'", payload["id"], classification)
                return

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

        # Префиксы: автоапрув и темы (теги)
        try:
            prefixes: List[str] = []
            moderation = payload.get("moderation") or {}
            if moderation.get("auto_approved") and str(moderation.get("classification")).lower() == "news":
                prefixes.append("✅ Автоапрув новостей")
            # Добавим явную метку классификации
            cls = str(moderation.get("classification") or "").lower()
            if cls:
                prefixes.append(f"🏷 Классификация: {'Новости' if cls == 'news' else 'Другое'}")
            topics = payload.get("topics") or []
            if topics:
                prefixes.append("🔖 Теги: " + " ".join(topics))
            if prefixes:
                prefix_text = "\n".join(prefixes) + "\n"
                shift = self._utf16_len(prefix_text)
                final_text = prefix_text + final_text
                shifted_entities = []
                for e in final_entities or []:
                    e2 = dict(e)
                    if isinstance(e2.get("offset"), int):
                        e2["offset"] = e2["offset"] + shift
                    else:
                        try:
                            e2["offset"] = int(e2.get("offset", 0)) + shift
                        except Exception:
                            pass
                    shifted_entities.append(e2)
                final_entities = shifted_entities
        except Exception:
            # не прерываем отправку, если что-то пошло не так
            pass

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

        # Тихие часы: отправляем без уведомлений
        try:
            if self.is_quiet_now():
                body["disable_notification"] = True
        except Exception:
            pass

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

    # Уведомляет в канал редакторов, что требуется авторизация, с кнопкой запуска.
    async def notify_auth_required(self) -> None:
        """Уведомляет в чат бота/админа, что требуется авторизация, с кнопкой запуска."""
        if not settings.BOT_TOKEN or not settings.ADMIN_CHAT_ID:
            logger.warning("BOT_TOKEN or ADMIN_CHAT_ID not configured. Skipping auth notification.")
            return
        # Определяем номер телефона для контекста уведомления
        phone_hint = getattr(self, "_auth_phone", None) or (settings.PHONE_NUMBER or "не указан")
        text = (
            "❗ Требуется авторизация MTProto аккаунта для коллектора.\n"
            f"Номер: {phone_hint}\n"
            "Нажмите кнопку ниже, затем пришлите код из SMS/звонка в ответном сообщении."
        )
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "🔐 Авторизоваться", "callback_data": "auth:start"}
                ]
            ]
        }
        body = {
            "chat_id": settings.ADMIN_CHAT_ID,
            "text": text,
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

        await asyncio.to_thread(_post_json, api_url, body)

    def auth_status(self) -> Dict[str, Any]:
        return {
            "authorized": self._authorized,
            "awaiting_code": self._await_code,
            "awaiting_password": self._await_password,
            "phone": self._auth_phone,
            "chat_id": self._auth_chat_id,
        }

    async def start_auth(self, phone: Optional[str], chat_id: Optional[int] = None) -> bool:
        """Старт авторизации: отправляет код на номер телефона.
        Если phone не задан — берём settings.PHONE_NUMBER. Сохраняем chat_id, чтобы ожидать ввод в нужном чате.
        """
        try:
            if not self.client.is_connected():
                await self.client.connect()
            # Если уже авторизованы — ничего не делаем
            self._authorized = await self.client.is_user_authorized()
            if self._authorized:
                self._await_code = False
                self._await_password = False
                return True

            # Выбираем номер телефона
            phone_num = (phone or settings.PHONE_NUMBER or '').strip()
            if not phone_num:
                logger.error("PHONE_NUMBER not provided and settings.PHONE_NUMBER is empty")
                return False
            self._auth_phone = phone_num
            self._auth_chat_id = chat_id
            # Запрашиваем код
            res = await self.client.send_code_request(phone_num)
            # Telethon возвращает структуру с phone_code_hash
            try:
                self._auth_hash = getattr(res, 'phone_code_hash', None)
            except Exception:
                self._auth_hash = None
            self._await_code = True
            self._await_password = False
            logger.info("Auth code requested for %s", phone_num)
            return True
        except Exception as e:
            logger.exception("start_auth failed: %s", e)
            return False

    async def submit_code(self, code: str) -> str:
        """Принимает код из SMS/звонка и завершает вход, либо включает режим запроса 2FA пароля.
        Возвращает: 'ok' | 'password_required' | 'error:<msg>'
        """
        code = (code or '').strip()
        if not code:
            return "error:empty_code"
        if not self._await_code or not self._auth_phone:
            return "error:not_waiting_code"
        try:
            if not self.client.is_connected():
                await self.client.connect()
            try:
                await self.client.sign_in(phone=self._auth_phone, code=code)
            except SessionPasswordNeededError:
                # Нужен 2FA пароль
                self._await_password = True
                self._await_code = False
                logger.info("2FA password required for %s", self._auth_phone)
                return "password_required"
            except PhoneCodeInvalidError:
                logger.warning("Invalid phone code entered for %s", self._auth_phone)
                return "error:invalid_code"
            # Успешная авторизация
            self._authorized = await self.client.is_user_authorized()
            self._await_code = False
            self._await_password = False
            logger.info("Authorized after code for %s: %s", self._auth_phone, self._authorized)
            if self._authorized:
                self._post_auth_start_handlers()
            return "ok" if self._authorized else "error:not_authorized"
        except Exception as e:
            logger.exception("submit_code failed: %s", e)
            return f"error:{str(e)}"

    async def submit_password(self, password: str) -> bool:
        """Ввод 2FA пароля, завершение авторизации."""
        password = (password or '').strip()
        if not password:
            return False
        if not self._await_password:
            return False
        try:
            if not self.client.is_connected():
                await self.client.connect()
            await self.client.sign_in(password=password)
            self._authorized = await self.client.is_user_authorized()
            self._await_password = False
            self._await_code = False
            logger.info("Authorized after 2FA password for %s: %s", self._auth_phone, self._authorized)
            if self._authorized:
                self._post_auth_start_handlers()
            return self._authorized
        except Exception as e:
            logger.exception("submit_password failed: %s", e)
            return False

    def _is_duplicate_and_mark(self, channel_id: Optional[int], message_id: Optional[int]) -> bool:
        """Return True if (channel_id,message_id) was already processed recently; otherwise mark it.
        Keeps a sliding window of last self._recent_max keys.
        """
        if channel_id is None or message_id is None:
            return False
        key = f"{channel_id}_{message_id}"
        if key in self._recent_set:
            logger.debug("Duplicate detected, skipping send to editors: %s", key)
            return True
        self._recent_set.add(key)
        self._recent_keys.append(key)
        if len(self._recent_keys) > self._recent_max:
            old = self._recent_keys.popleft()
            self._recent_set.discard(old)
        return False

    def _is_ad_or_promo(self, text: Optional[str]) -> bool:
        """Грубая проверка на рекламный/партнёрский пост по ключевым словам.
        Возвращает True, если текст содержит один из ключевых паттернов.
        """
        if not self._ad_filter_enabled:
            return False
        t = (text or "").lower()
        if not t:
            return False
        for w in self._ad_filter_words:
            if w and w in t:
                return True
        return False

    # ---- Auto-approval and classification helpers ----
    def _get_auto_approve_flags(self) -> Dict[str, bool]:
        return {
            "use_classify": bool(settings.USE_GEMINI_CLASSIFY),
            "send_news_to_approval": bool(settings.SEND_NEWS_TO_APPROVAL),
            "send_others_to_approval": bool(settings.SEND_OTHERS_TO_APPROVAL),
            "auto_publish_news": bool(settings.AUTO_PUBLISH_NEWS),
        }

    async def _classify_post(self, text: Optional[str]) -> str:
        """Return 'news' or 'other'. If classification disabled, treat as 'other'."""
        if not settings.USE_GEMINI_CLASSIFY:
            return "other"
        t = (text or "").strip()
        if not t:
            return "other"
        # Try external classifier first
        try:
            base = (settings.CLASSIFIER_URL or "").rstrip("/")
            if base:
                url = base + "/api/classifier/classify"
                payload = {"text": t}
                req = urlrequest.Request(
                    url,
                    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with urlrequest.urlopen(req, timeout=5) as resp:
                    status = getattr(resp, "status", 200)
                    body = resp.read().decode("utf-8")
                if status == 200:
                    try:
                        data = json.loads(body)
                    except Exception:
                        data = None
                    if isinstance(data, dict) and data.get("ok") is True:
                        return "news" if bool(data.get("is_news")) else "other"
        except HTTPError as he:
            logger.warning(f"Classifier HTTPError: {he.code}")
        except URLError as ue:
            logger.warning(f"Classifier URLError: {ue}")
        except Exception as e:
            logger.warning(f"Classifier call failed: {e}")
        # Fallback to local heuristic
        lower = t.lower()
        keywords = [
            "news", "breaking", "urgent", "report:", "reported",
            "срочно", "новость", "источник", "заявил", "пресс-служба",
        ]
        score = sum(1 for w in keywords if w in lower)
        if score >= 1 and len(t) > 50:
            return "news"
        return "other"

    def _decide_auto_approval(self, classification: str) -> Dict[str, bool]:
        f = self._get_auto_approve_flags()
        cls = (classification or "").lower()
        if cls == "news":
            auto = f["auto_publish_news"] and not f["send_news_to_approval"]
            return {"auto_approve": auto, "send_to_approval": f["send_news_to_approval"]}
        else:
            # Любая не-новость идёт в ручное утверждение согласно настройке для "other"
            return {"auto_approve": False, "send_to_approval": f["send_others_to_approval"]}

    async def _on_new_message(self, event: events.NewMessage.Event) -> None:
        """Обработка одиночного нового сообщения (не альбом)."""
        try:
            msg: Message = event.message
            if not msg:
                return
            # Альбомы обрабатываются в _on_new_album
            if getattr(msg, "grouped_id", None):
                return

            chat = await event.get_chat()
            channel_id = getattr(chat, "id", None)
            channel_username = getattr(chat, "username", None)
            channel_title = getattr(chat, "title", None) or channel_username or "unknown"

            # Простая фильтрация рекламы/продвижения
            if self._is_ad_or_promo(msg.message):
                logger.info(
                    "Ad/promo detected, skipping message %s from channel '%s'",
                    f"{channel_id}_{getattr(msg, 'id', None)}",
                    channel_title,
                )
                return

            # De-duplication
            if self._is_duplicate_and_mark(channel_id, getattr(msg, "id", None)):
                return

            # Метаданные
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

            # Extract topics (hashtags) from message text
            topics: List[str] = []
            try:
                t = msg.message or ""
                if t:
                    seen = set()
                    for m in re.finditer(r"(?<!\w)#([\w\d_А-Яа-яЁё]+)", t, flags=re.UNICODE):
                        tag = "#" + m.group(1)
                        if tag not in seen:
                            seen.add(tag)
                            topics.append(tag)
            except Exception:
                topics = []

            payload: Dict[str, Any] = {
                "id": f"{channel_id}_{msg.id}",
                "channel_id": str(channel_id),
                "channel_name": str(channel_title),
                "channel_username": channel_username,
                "channel_title": channel_title,
                "message_id": msg.id,
                "text": msg.message,
                "media": None,
                "author": author,
                "timestamp": msg.date.isoformat() if msg.date else None,
                "metadata": {
                    "views": views,
                    "forwards": forwards,
                    "reactions": reactions,
                },
                "topics": topics,
                "status": "pending",
                "moderation": None,
            }

            classification = await self._classify_post(msg.message)
            decision = self._decide_auto_approval(classification)

            if decision.get("auto_approve"):
                payload["status"] = "approved"
                payload["moderation"] = {"classification": classification, "auto_approved": True}
                path = save_approved_message(settings.APPROVED_DIR, payload)
                logger.info(f"Saved approved message: {path}")
                return
            elif decision.get("send_to_approval"):
                payload["moderation"] = {"classification": classification, "auto_approved": False}
                path = save_pending_message(settings.PENDING_DIR, payload)
                logger.info(f"Saved pending message: {path}")
                await self._send_to_editors(payload, path, source_message=msg)
                return
            else:
                logger.info("Dropping message %s after classification '%s'", payload["id"], classification)
                return

        except Exception as e:
            logger.exception(f"Failed to process new message: {e}")


    async def _on_new_album(self, event: events.Album.Event) -> None:
        """Обрабатываем альбом (media group) как единый пост: пересылаем только текстовую часть (капшен),
        сохраняя форматирование, без дублирования по каждому медиа."""
        try:
            msgs: List[Message] = list(event.messages) if hasattr(event, "messages") else []
            # Игнорируем альбомы из одного элемента (во избежание дублей с NewMessage)
            if not msgs or len(msgs) <= 1:
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
            # Простая фильтрация рекламы/продвижения
            if self._is_ad_or_promo(msg.message):
                logger.info("Ad/promo detected, skipping album %s from channel '%s'", f"{channel_id}_{getattr(msg, 'id', None)}", channel_title)
                return

            # De-duplication guard (используем id выбранного сообщения альбома)
            group_id = getattr(msg, "grouped_id", None) or (getattr(msgs[0], "grouped_id", None) if msgs else None)
            if self._is_duplicate_and_mark(channel_id, group_id):
                return

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

            # Extract topics (hashtags) from album caption
            topics: List[str] = []
            try:
                t = msg.message or ""
                if t:
                    seen = set()
                    for m in re.finditer(r"(?<!\w)#([\w\d_А-Яа-яЁё]+)", t, flags=re.UNICODE):
                        tag = "#" + m.group(1)
                        if tag not in seen:
                            seen.add(tag)
                            topics.append(tag)
            except Exception:
                topics = []

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
                "topics": topics,
                "status": "pending",
                "moderation": None,
            }

            classification = await self._classify_post(msg.message)
            decision = self._decide_auto_approval(classification)

            if decision.get("auto_approve"):
                payload["status"] = "approved"
                payload["moderation"] = {"classification": classification, "auto_approved": True}
                path = save_approved_message(settings.APPROVED_DIR, payload)
                logger.info(f"Saved approved album message: {path}")
                return
            elif decision.get("send_to_approval"):
                payload["moderation"] = {"classification": classification, "auto_approved": False}
                path = save_pending_message(settings.PENDING_DIR, payload)
                logger.info(f"Saved pending album message: {path}")
                await self._send_to_editors(payload, path, source_message=msg)
                return
            else:
                logger.info("Dropping album %s after classification '%s'", payload["id"], classification)
                return

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

        # Префиксы: автоапрув и темы (теги)
        try:
            prefixes: List[str] = []
            moderation = payload.get("moderation") or {}
            if moderation.get("auto_approved") and str(moderation.get("classification")).lower() == "news":
                prefixes.append("✅ Автоапрув новостей")
            topics = payload.get("topics") or []
            if topics:
                prefixes.append("🔖 Теги: " + " ".join(topics))
            if prefixes:
                prefix_text = "\n".join(prefixes) + "\n"
                shift = self._utf16_len(prefix_text)
                final_text = prefix_text + final_text
                shifted_entities = []
                for e in final_entities or []:
                    e2 = dict(e)
                    if isinstance(e2.get("offset"), int):
                        e2["offset"] = e2["offset"] + shift
                    else:
                        try:
                            e2["offset"] = int(e2.get("offset", 0)) + shift
                        except Exception:
                            pass
                    shifted_entities.append(e2)
                final_entities = shifted_entities
        except Exception:
            # не прерываем отправку, если что-то пошло не так
            pass

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

        # Тихие часы: отправляем без уведомлений
        try:
            if self.is_quiet_now():
                body["disable_notification"] = True
        except Exception:
            pass

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

    # Уведомляет в канал редакторов, что требуется авторизация, с кнопкой запуска.
    async def notify_auth_required(self) -> None:
        """Уведомляет в чат бота/админа, что требуется авторизация, с кнопкой запуска."""
        if not settings.BOT_TOKEN or not settings.ADMIN_CHAT_ID:
            logger.warning("BOT_TOKEN or ADMIN_CHAT_ID not configured. Skipping auth notification.")
            return
        # Определяем номер телефона для контекста уведомления
        phone_hint = getattr(self, "_auth_phone", None) or (settings.PHONE_NUMBER or "не указан")
        text = (
            "❗ Требуется авторизация MTProto аккаунта для коллектора.\n"
            f"Номер: {phone_hint}\n"
            "Нажмите кнопку ниже, затем пришлите код из SMS/звонка в ответном сообщении."
        )
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "🔐 Авторизоваться", "callback_data": "auth:start"}
                ]
            ]
        }
        body = {
            "chat_id": settings.ADMIN_CHAT_ID,
            "text": text,
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

        await asyncio.to_thread(_post_json, api_url, body)

    def auth_status(self) -> Dict[str, Any]:
        return {
            "authorized": self._authorized,
            "awaiting_code": self._await_code,
            "awaiting_password": self._await_password,
            "phone": self._auth_phone,
            "chat_id": self._auth_chat_id,
        }

    async def start_auth(self, phone: Optional[str], chat_id: Optional[int] = None) -> bool:
        """Старт авторизации: отправляет код на номер телефона.
        Если phone не задан — берём settings.PHONE_NUMBER. Сохраняем chat_id, чтобы ожидать ввод в нужном чате.
        """
        try:
            if not self.client.is_connected():
                await self.client.connect()
            # Если уже авторизованы — ничего не делаем
            self._authorized = await self.client.is_user_authorized()
            if self._authorized:
                self._await_code = False
                self._await_password = False
                return True

            # Выбираем номер телефона
            phone_num = (phone or settings.PHONE_NUMBER or '').strip()
            if not phone_num:
                logger.error("PHONE_NUMBER not provided and settings.PHONE_NUMBER is empty")
                return False
            self._auth_phone = phone_num
            self._auth_chat_id = chat_id
            # Запрашиваем код
            res = await self.client.send_code_request(phone_num)
            # Telethon возвращает структуру с phone_code_hash
            try:
                self._auth_hash = getattr(res, 'phone_code_hash', None)
            except Exception:
                self._auth_hash = None
            self._await_code = True
            self._await_password = False
            logger.info("Auth code requested for %s", phone_num)
            return True
        except Exception as e:
            logger.exception("start_auth failed: %s", e)
            return False

    async def submit_code(self, code: str) -> str:
        """Принимает код из SMS/звонка и завершает вход, либо включает режим запроса 2FA пароля.
        Возвращает: 'ok' | 'password_required' | 'error:<msg>'
        """
        code = (code or '').strip()
        if not code:
            return "error:empty_code"
        if not self._await_code or not self._auth_phone:
            return "error:not_waiting_code"
        try:
            if not self.client.is_connected():
                await self.client.connect()
            try:
                await self.client.sign_in(phone=self._auth_phone, code=code)
            except SessionPasswordNeededError:
                # Нужен 2FA пароль
                self._await_password = True
                self._await_code = False
                logger.info("2FA password required for %s", self._auth_phone)
                return "password_required"
            except PhoneCodeInvalidError:
                logger.warning("Invalid phone code entered for %s", self._auth_phone)
                return "error:invalid_code"
            # Успешная авторизация
            self._authorized = await self.client.is_user_authorized()
            self._await_code = False
            self._await_password = False
            logger.info("Authorized after code for %s: %s", self._auth_phone, self._authorized)
            if self._authorized:
                self._post_auth_start_handlers()
            return "ok" if self._authorized else "error:not_authorized"
        except Exception as e:
            logger.exception("submit_code failed: %s", e)
            return f"error:{str(e)}"

    async def submit_password(self, password: str) -> bool:
        """Ввод 2FA пароля, завершение авторизации."""
        password = (password or '').strip()
        if not password:
            return False
        if not self._await_password:
            return False
        try:
            if not self.client.is_connected():
                await self.client.connect()
            await self.client.sign_in(password=password)
            self._authorized = await self.client.is_user_authorized()
            self._await_password = False
            self._await_code = False
            logger.info("Authorized after 2FA password for %s: %s", self._auth_phone, self._authorized)
            if self._authorized:
                self._post_auth_start_handlers()
            return self._authorized
        except Exception as e:
            logger.exception("submit_password failed: %s", e)
            return False

    def _is_duplicate_and_mark(self, channel_id: Optional[int], message_id: Optional[int]) -> bool:
        """Return True if (channel_id,message_id) was already processed recently; otherwise mark it.
        Keeps a sliding window of last self._recent_max keys.
        """
        if channel_id is None or message_id is None:
            return False
        key = f"{channel_id}_{message_id}"
        if key in self._recent_set:
            logger.debug("Duplicate detected, skipping send to editors: %s", key)
            return True
        self._recent_set.add(key)
        self._recent_keys.append(key)
        if len(self._recent_keys) > self._recent_max:
            old = self._recent_keys.popleft()
            self._recent_set.discard(old)
        return False

    def _is_ad_or_promo(self, text: Optional[str]) -> bool:
        """Грубая проверка на рекламный/партнёрский пост по ключевым словам.
        Возвращает True, если текст содержит один из ключевых паттернов.
        """
        if not self._ad_filter_enabled:
            return False
        t = (text or "").lower()
        if not t:
            return False
        for w in self._ad_filter_words:
            if w and w in t:
                return True
        return False


    async def _on_new_album(self, event: events.Album.Event) -> None:
        """Обрабатываем альбом (media group) как единый пост: пересылаем только текстовую часть (капшен),
        сохраняя форматирование, без дублирования по каждому медиа."""
        try:
            msgs: List[Message] = list(event.messages) if hasattr(event, "messages") else []
            # Игнорируем альбомы из одного элемента (во избежание дублей с NewMessage)
            if not msgs or len(msgs) <= 1:
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
            # Простая фильтрация рекламы/продвижения
            if self._is_ad_or_promo(msg.message):
                logger.info("Ad/promo detected, skipping album %s from channel '%s'", f"{channel_id}_{getattr(msg, 'id', None)}", channel_title)
                return

            # De-duplication guard (используем id выбранного сообщения альбома)
            group_id = getattr(msg, "grouped_id", None) or (getattr(msgs[0], "grouped_id", None) if msgs else None)
            if self._is_duplicate_and_mark(channel_id, group_id):
                return

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

            classification = await self._classify_post(msg.message)
            decision = self._decide_auto_approval(classification)

            if decision.get("auto_approve"):
                payload["status"] = "approved"
                payload["moderation"] = {"classification": classification, "auto_approved": True}
                path = save_approved_message(settings.APPROVED_DIR, payload)
                logger.info(f"Saved approved album message: {path}")
                return
            elif decision.get("send_to_approval"):
                payload["moderation"] = {"classification": classification, "auto_approved": False}
                path = save_pending_message(settings.PENDING_DIR, payload)
                logger.info(f"Saved pending album message: {path}")
                await self._send_to_editors(payload, path, source_message=msg)
                return
            else:
                logger.info("Dropping album %s after classification '%s'", payload["id"], classification)
                return

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