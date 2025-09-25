import logging
import os
import json
import asyncio
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError
from datetime import datetime

# Подхватим .env из корня проекта при локальном запуске
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_PATH = os.path.join(BASE_DIR, ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

from .config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("assistant.main")

app = FastAPI(title="MediaGenerator Assistant", version="0.3.0")

# --- Ежедневный планировщик дайджеста ---
_scheduler_task: Optional[asyncio.Task] = None
# Гейтинг, чтобы не триггерить публикацию дважды в одну и ту же минуту
_fired_date = None
_fired_times: set[str] = set()


def _now_date_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _parse_hhmm(s: str) -> Optional[tuple[int, int]]:
    try:
        hh, mm = s.split(":", 1)
        h, m = int(hh), int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
        return None
    except Exception:
        return None


async def _digest_scheduler() -> None:
    logger.info("Scheduler started")
    global _fired_date, _fired_times
    while True:
        try:
            cfg = _load_agg_config()
            # Поддержка старого формата: schedule (строка) -> schedules (list)
            schedules = cfg.get("schedules") or ([cfg.get("schedule")] if cfg.get("schedule") else [])
            schedules = [s.strip() for s in schedules if isinstance(s, str) and _parse_hhmm(s.strip())]
            agg_url_set = bool(settings.AGGREGATOR_URL)

            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            hhmm_now = now.strftime("%H:%M")

            # Сбросим гейтинг при смене дня
            if _fired_date != today:
                _fired_date = today
                _fired_times = set()

            if schedules and agg_url_set:
                if hhmm_now in schedules and hhmm_now not in _fired_times:
                    logger.info(
                        f"Scheduler: publish time reached: schedules={schedules}, now={now.isoformat()}"
                    )
                    limit = cfg.get("limit")
                    url = settings.AGGREGATOR_URL.rstrip("/") + "/api/aggregator/publish_now"
                    if isinstance(limit, int) and limit > 0:
                        url = f"{url}?limit={int(limit)}"
                    logger.info(f"Scheduler: triggering publish: {url}")
                    resp = _rest_call("POST", url, {}) or {}
                    ok = resp.get("ok")
                    result = resp.get("result")
                    published = resp.get("published")
                    err = resp.get("error")
                    removed = resp.get("removed")
                    logger.info(
                        f"Scheduler: publish response ok={ok} result={result} published={published} error={err} removed_count={len(removed or [])}"
                    )
                    # Помечаем этот слот как отработанный, чтобы не повторять публикацию каждую секунду в эту минуту
                    _fired_times.add(hhmm_now)
                # else: умышленно не логируем каждую итерацию, чтобы избежать спама
            else:
                if not schedules:
                    logger.info("Scheduler: schedules not set; skipping")
                if not agg_url_set:
                    logger.info("Scheduler: AGGREGATOR_URL is not set; skipping")
        except Exception:
            logger.exception("Scheduler tick error")
        await asyncio.sleep(30)


@app.on_event("startup")
async def on_startup():
    # Убедимся, что директории существуют
    os.makedirs(settings.PENDING_DIR, exist_ok=True)
    os.makedirs(settings.APPROVED_DIR, exist_ok=True)
    # Директория конфигурации агрегатора
    os.makedirs(os.path.dirname(settings.AGGREGATOR_CONFIG_PATH), exist_ok=True)
    logger.info("Assistant service started (webhook mode)")
    # Логируем версию сервиса при запуске
    try:
        logger.info("Assistant version: %s", getattr(app, "version", "unknown"))
    except Exception:
        pass

    # Логируем стартовую конфигурацию планировщика
    try:
        cfg = _load_agg_config()
        schedules = cfg.get("schedules") or ([cfg.get("schedule")] if cfg.get("schedule") else [])
        logger.info(
            "Scheduler config: schedules=%s, limit=%s, aggregator_url=%s",
            schedules, cfg.get("limit"), ("set" if settings.AGGREGATOR_URL else "not set"),
        )
    except Exception:
        logger.warning("Failed to load scheduler config on startup")

    # Запускаем фоновый планировщик публикаций
    global _scheduler_task
    if _scheduler_task is None:
        _scheduler_task = asyncio.create_task(_digest_scheduler())

    # Обновление команд бота (для всплывающих подсказок)
    try:
        _update_bot_commands()
        logger.info("Bot commands updated")
    except Exception:
        logger.warning("Failed to update bot commands")

    # Автоконфигурация вебхука
    if not settings.SERVICE_URL:
        logger.warning("SERVICE_URL_ASSISTANT не задан — пропускаю автоконфигурацию вебхука")
        return

    target_url = settings.SERVICE_URL.rstrip("/") + "/telegram/webhook"

    # 1) Узнаем текущий webhook
    info = _tg_api("getWebhookInfo", {})
    curr_url = (info or {}).get("result", {}).get("url") if isinstance(info, dict) else None

    # 2) Если вебхук не совпадает — выставляем
    if curr_url != target_url:
        body = {
            "url": target_url,
            # Небольшие ограничения для снижения нагрузки
            "max_connections": 20,
            "allowed_updates": ["message", "callback_query"],
        }
        if settings.WEBHOOK_SECRET:
            body["secret_token"] = settings.WEBHOOK_SECRET
        set_res = _tg_api("setWebhook", body)
        ok = bool(set_res and set_res.get("ok", False))
        if ok:
            logger.info(f"Webhook set to: {target_url}")
        else:
            logger.warning(f"Failed to set webhook to: {target_url}")
    else:
        logger.info("Webhook already configured correctly")


@app.get("/health")
async def health():
    try:
        wh_info = _tg_api("getWebhookInfo", {}) or {}
        result = wh_info.get("result", {}) if isinstance(wh_info, dict) else {}
    except Exception:
        result = {}
    try:
        cfg = _load_agg_config()
    except Exception:
        cfg = {}
    return JSONResponse({
        "ok": True,
        "status": "ok",
        "service": "assistant",
        "webhook": result,
        "scheduler": {
            "schedules": (cfg.get("schedules") or ([cfg.get("schedule")] if cfg.get("schedule") else [])),
            "limit": cfg.get("limit"),
        }
    })


@app.get("/debug/webhook-info")
async def debug_webhook_info():
    info = _tg_api("getWebhookInfo", {})
    return JSONResponse(info or {"ok": False})


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
            text = he.read().decode("utf-8")
            logger.warning(f"Bot API HTTPError: method={method}, status={he.code}, body={text}")
        except Exception:
            logger.warning(f"Bot API HTTPError: method={method}, status={he.code}")
    except URLError as ue:
        logger.warning(f"Bot API URLError: method={method}, err={ue}")
    except Exception:
        logger.exception(f"Bot API error: method={method}")
    return None


def _send_message(chat_id: int, text: str, reply_to_message_id: Optional[int] = None) -> None:
    body: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
        "parse_mode": "Markdown",
    }
    if reply_to_message_id:
        body["reply_to_message_id"] = reply_to_message_id
        body["allow_sending_without_reply"] = True
    _tg_api("sendMessage", body)


def _answer_callback(callback_id: Optional[str], text: str) -> None:
    if not callback_id:
        return
    _tg_api("answerCallbackQuery", {"callback_query_id": callback_id, "text": text, "show_alert": False})


def _delete_message(chat_id: Optional[int], message_id: Optional[int]) -> bool:
    if not chat_id or not message_id:
        return False
    resp = _tg_api("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
    return bool(resp and resp.get("ok"))


def _clear_markup(chat_id: Optional[int], message_id: Optional[int]) -> bool:
    if not chat_id or not message_id:
        return False
    resp = _tg_api("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id, "reply_markup": {}})
    return bool(resp and resp.get("ok"))


# --- Авторизация Collector через бота ---
_AUTH_WAIT: dict[int, str] = {}

def _start_auth_flow(chat_id: int) -> None:
    # Если Collector недоступен — сообщим
    h = _rest_call("GET", settings.COLLECTOR_URL + "/health") or {}
    if not (h.get("status") == "ok" or h.get("authorized") in (True, False)):
        _send_message(chat_id, "Collector недоступен. Попробуйте позже.")
        return

    # Стартуем авторизацию: используем ADMIN_CHAT_ID как приоритетный канал управления
    target_chat = settings.ADMIN_CHAT_ID or chat_id
    # Определяем телефон из статуса, если доступен
    phone_hint = None
    try:
        st = _rest_call("GET", settings.COLLECTOR_URL + "/api/collector/auth/status") or {}
        phone_hint = ((st.get("status") or {}).get("phone") or None)
    except Exception:
        phone_hint = None

    _AUTH_WAIT[target_chat] = "phone"
    if phone_hint:
        _send_message(target_chat, f"Введите телефон (например, +79991234567). Текущий: {phone_hint}")
    else:
        _send_message(target_chat, "Введите телефон (например, +79991234567)")


def _handle_auth_input(chat_id: int, text: str) -> None:
    step = _AUTH_WAIT.get(chat_id)
    if not step:
        _send_message(chat_id, "Нет активного процесса авторизации. Нажмите кнопку Авторизовать в боте.")
        return

    if step == "phone":
        phone = text.strip()
        res = _rest_call("POST", settings.COLLECTOR_URL + "/api/collector/auth/start", {"phone": phone}) or {}
        if not res.get("ok"):
            _send_message(chat_id, "Не удалось начать авторизацию. Попробуйте позже.")
            return
        _send_message(chat_id, "Отправьте код, полученный в Telegram (или 'cancel' для отмены)")
        _AUTH_WAIT[chat_id] = "code"
        return

    if step == "code":
        code = text.strip()
        if code.lower() == "cancel":
            _AUTH_WAIT.pop(chat_id, None)
            _send_message(chat_id, "Авторизация отменена")
            return
        resp = _rest_call("POST", settings.COLLECTOR_URL.rstrip("/") + "/api/collector/auth/code", {"code": code}) or {}
        result = resp.get("result") or ""
        st = resp.get("status") or {}
        if resp.get("ok") or result == "ok" or (st.get("authorized")):
            _AUTH_WAIT.pop(chat_id, None)
            _send_message(chat_id, "Авторизация Collector завершена")
            return
        if result == "password_required" or st.get("await_password"):
            _AUTH_WAIT[chat_id] = "password"
            _send_message(chat_id, "Требуется пароль 2FA. Введите пароль")
            return
        _send_message(chat_id, "Код неверный или истёк. Попробуйте ещё раз или 'cancel' для отмены")
        return

    if step == "password":
        password = text.strip()
        resp = _rest_call("POST", settings.COLLECTOR_URL.rstrip("/") + "/api/collector/auth/password", {"password": password}) or {}
        st = resp.get("status") or {}
        if resp.get("ok") or st.get("authorized"):
            _AUTH_WAIT.pop(chat_id, None)
            _send_message(chat_id, "Авторизация Collector завершена")
            return
        _send_message(chat_id, "Пароль не принят. Попробуйте снова")
        return


def _approve(filename: str) -> bool:
    try:
        src = os.path.join(settings.PENDING_DIR, filename)
        if not os.path.exists(src):
            return False
        dst = os.path.join(settings.APPROVED_DIR, filename)
        os.replace(src, dst)
        logger.info(f"Approved: {filename}")
        # Автопубликация после одобрения: вызываем агрегатор с задержкой, если настроено
        try:
            if settings.AUTO_PUBLISH_NEWS and settings.AGGREGATOR_URL:
                url = settings.AGGREGATOR_URL.rstrip("/") + "/api/aggregator/publish_soon"
                resp = _rest_call("POST", url, {}, timeout=180) or {}
                logger.info(
                    f"Auto-publish scheduled: ok={resp.get('ok')} result={resp.get('result')} published={resp.get('published')} error={resp.get('error')}"
                )
        except Exception:
            logger.exception("Auto-publish on approve failed")
        return True
    except Exception:
        logger.exception("Approve failed")
        return False


def _reject(filename: str) -> bool:
    try:
        # Сначала пробуем удалить из approved (отмена автоапрува)
        approved_path = os.path.join(settings.APPROVED_DIR, filename)
        pending_path = os.path.join(settings.PENDING_DIR, filename)
        if os.path.exists(approved_path):
            os.remove(approved_path)
            logger.info(f"Rejected (removed from approved): {filename}")
            return True
        # Иначе удаляем из pending
        if os.path.exists(pending_path):
            os.remove(pending_path)
            logger.info(f"Rejected: {filename}")
            return True
        return False
    except Exception:
        logger.exception("Reject failed")
        return False


def _rest_call(method: str, url: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 120) -> Optional[Dict[str, Any]]:
    try:
        data = None
        headers = {"Content-Type": "application/json"}
        if method.upper() in ("POST", "PUT", "PATCH"):
            data = json.dumps(payload or {}).encode("utf-8")
        req = urlrequest.Request(url, data=data, headers=headers, method=method.upper())
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")
            try:
                return json.loads(text)
            except Exception:
                logger.warning(f"REST call returned non-JSON: {text[:200]}")
                return None
    except HTTPError as he:
        try:
            t = he.read().decode("utf-8")
        except Exception:
            t = str(he)
        logger.warning(f"REST HTTPError: {method} {url} -> {he.code} {t}")
    except URLError as ue:
        logger.warning(f"REST URLError: {method} {url} -> {ue}")
    except Exception:
        logger.exception(f"REST error: {method} {url}")
    return None


def _load_agg_config() -> Dict[str, Any]:
    try:
        if not os.path.exists(settings.AGGREGATOR_CONFIG_PATH):
            return {}
        with open(settings.AGGREGATOR_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.warning("Failed to read aggregator config; using defaults")
        return {}


def _save_agg_config(cfg: Dict[str, Any]) -> bool:
    try:
        os.makedirs(os.path.dirname(settings.AGGREGATOR_CONFIG_PATH), exist_ok=True)
        with open(settings.AGGREGATOR_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        logger.exception("Failed to write aggregator config")
        return False


def _update_bot_commands() -> None:
    cmds = [
        {"command": "help", "description": "Справка по доступным командам"},
        {"command": "add_source", "description": "Добавить источник: @channel или t.me/link"},
        {"command": "remove_source", "description": "Удалить источник"},
        {"command": "list_sources", "description": "Список источников"},
        {"command": "quiet", "description": "Тихий режим on/off"},
        {"command": "quiet_schedule", "description": "Настроить тихие часы HH:MM-HH:MM или off"},
        {"command": "digest_time", "description": "Время(а) публикации дайджеста"},
        {"command": "digest_limit", "description": "Лимит постов в дайджесте"},
        {"command": "publish_now", "description": "Запустить публикацию сейчас"},
        {"command": "status", "description": "Показать статусы и настройки"},
        {"command": "autoapprove_news", "description": "Автоапрув новостей on/off"},
        {"command": "autoapprove_expert", "description": "Автоапрув аналитики on/off"},
        {"command": "classify", "description": "Классификация постов on/off"},
        {"command": "news_to_approval", "description": "Новости на апрув on/off"},
        {"command": "others_to_approval", "description": "Прочие посты на апрув on/off"},
    ]
    try:
        _tg_api("setMyCommands", {"commands": cmds})
    except Exception:
        logger.warning("Failed to set bot commands")


def _help_text() -> str:
    lines = [
        "Доступные команды:",
        "/help — показать справку",
        "/add_source <@channel|t.me/link> — добавить источник",
        "/remove_source <@channel|t.me/link> — удалить источник",
        "/list_sources — показать список источников",
        "/quiet on|off — включить/выключить тихий режим",
        "/quiet_schedule <HH:MM-HH:MM|off> — настроить тихие часы",
        "/digest_time <HH:MM[,HH:MM ...]> — установить время(а) публикации",
        "/digest_limit <N> — ограничить число постов в дайджесте",
        "/publish_now — запустить публикацию сейчас",
        "/status — показать статусы сервисов",
        "/autoapprove_news on|off — включить/выключить автоапрув новостей",
        "/autoapprove_expert on|off — включить/выключить автоапрув аналитики/экспертного",
        "/classify on|off — включить/выключить классификацию постов",
        "/news_to_approval on|off — отправлять новости на апрув",
        "/others_to_approval on|off — отправлять прочие посты на апрув",
    ]
    return "\n".join(lines)


def _validate_hhmm(s: str) -> bool:
    return _parse_hhmm((s or "").strip()) is not None


def _handle_command(chat_id: int, message_id: Optional[int], text: str) -> None:
    t = (text or "").strip()
    if not t.startswith("/"):
        return
    cmd, _, args = t.partition(" ")
    cmd = cmd.lower()
    args = args.strip()

    # Ограничим доступ по ADMIN_CHAT_ID, если задан
    if settings.ADMIN_CHAT_ID is not None and chat_id != settings.ADMIN_CHAT_ID:
        _send_message(chat_id, "Эта команда доступна только администратору.")
        return

    # Маршрутизация команд
    if cmd in ("/help", "/start"):
        _send_message(chat_id, _help_text(), reply_to_message_id=message_id)
        return

    if cmd == "/auth_start":
        _start_auth_flow(chat_id)
        return

    if cmd == "/add_source":
        if not args:
            _send_message(chat_id, "Использование: /add_source <@channel|t.me/link>")
            return
        url = settings.COLLECTOR_URL.rstrip("/") + "/api/collector/channels/add"
        resp = _rest_call("POST", url, {"channel": args})
        if not resp:
            _send_message(chat_id, "Ошибка: Collector недоступен")
            return
        if resp.get("ok") and resp.get("added"):
            _send_message(chat_id, f"Источник добавлен: {args}")
        elif resp.get("reason") == "duplicate":
            _send_message(chat_id, f"Источник уже существует: {args}")
        else:
            _send_message(chat_id, f"Не удалось добавить источник: {args}")
        return

    if cmd == "/remove_source":
        if not args:
            _send_message(chat_id, "Использование: /remove_source <@channel|t.me/link>")
            return
        url = settings.COLLECTOR_URL.rstrip("/") + "/api/collector/channels/remove"
        resp = _rest_call("POST", url, {"channel": args})
        if not resp:
            _send_message(chat_id, "Ошибка: Collector недоступен")
            return
        if resp.get("ok") and resp.get("removed"):
            _send_message(chat_id, f"Источник удалён: {args}")
        elif resp.get("reason") == "not_found":
            _send_message(chat_id, f"Источник не найден: {args}")
        else:
            _send_message(chat_id, f"Не удалось удалить источник: {args}")
        return

    if cmd == "/list_sources":
        url = settings.COLLECTOR_URL.rstrip("/") + "/api/collector/channels"
        resp = _rest_call("GET", url)
        if not resp or not resp.get("ok"):
            _send_message(chat_id, "Ошибка: Collector недоступен")
            return
        chs = resp.get("channels") or []
        if not chs:
            _send_message(chat_id, "Список источников пуст")
        else:
            txt = "Текущие источники (" + str(len(chs)) + "):\n" + "\n".join(chs)
            _send_message(chat_id, txt)
        return

    if cmd == "/quiet":
        val = args.lower()
        if val not in ("on", "off"):
            _send_message(chat_id, "Использование: /quiet on|off")
            return
        url = settings.COLLECTOR_URL.rstrip("/") + "/api/collector/quiet"
        resp = _rest_call("POST", url, {"on": val == "on"})
        if not resp or not resp.get("ok"):
            _send_message(chat_id, "Ошибка: Collector недоступен")
            return
        state = resp.get("quiet")
        _send_message(chat_id, f"Тихий режим: {'включен' if state else 'выключен'}")
        return

    if cmd == "/quiet_schedule":
        if not args:
            _send_message(chat_id, "Использование: /quiet_schedule <HH:MM-HH:MM|off>")
            return
        rng = args if args.lower() != "off" else ""
        url = settings.COLLECTOR_URL.rstrip("/") + "/api/collector/quiet/schedule"
        resp = _rest_call("POST", url, {"range": rng})
        if not resp or not resp.get("ok"):
            _send_message(chat_id, "Ошибка: Collector недоступен")
            return
        r = resp.get("range")
        if r:
            _send_message(chat_id, f"Тихие часы установлены: {r}")
        else:
            _send_message(chat_id, "Тихие часы отключены")
        return

    if cmd == "/autoapprove_news":
        val = args.lower()
        if val not in ("on", "off"):
            _send_message(chat_id, "Использование: /autoapprove_news on|off")
            return
        # First, update Collector flags to ensure ingestion behavior matches the toggle
        url = settings.COLLECTOR_URL.rstrip("/") + "/api/collector/autoapprove"
        resp = _rest_call("POST", url, {
            "auto_publish_news": (val == "on"),
            "send_news_to_approval": (val != "on"),
        })
        if not resp or not resp.get("ok"):
            _send_message(chat_id, "Ошибка: Collector недоступен")
            return
        flags = resp.get("flags") or {}
        # Then, keep aggregator config in sync
        cfg = _load_agg_config()
        cfg["auto_approve_news"] = (val == "on")
        _save_agg_config(cfg)
        # Report the effective collector flags
        def _onoff(v: bool) -> str:
            return "on" if v else "off"
        f1 = _onoff(bool(flags.get("use_classify")))
        f2 = _onoff(bool(flags.get("send_news_to_approval")))
        f3 = _onoff(bool(flags.get("auto_publish_news")))
        _send_message(
            chat_id,
            (
                f"Автоапрув новостей: {'включен' if (val == 'on') else 'выключен'}\n"
                f"Collector: use_classify={f1}, send_news_to_approval={f2}, auto_publish_news={f3}"
            )
        )
        return

    if cmd == "/autoapprove_expert":
        val = args.lower()
        if val not in ("on", "off"):
            _send_message(chat_id, "Использование: /autoapprove_expert on|off")
            return
        cfg = _load_agg_config()
        cfg["auto_approve_expert"] = (val == "on")
        if _save_agg_config(cfg):
            _send_message(chat_id, f"Автоапрув аналитики/экспертного: {'включен' if cfg['auto_approve_expert'] else 'выключен'}")
        else:
            _send_message(chat_id, "Не удалось сохранить конфигурацию")
        return

    if cmd == "/classify":
        val = args.lower()
        if val not in ("on", "off"):
            _send_message(chat_id, "Использование: /classify on|off")
            return
        url = settings.COLLECTOR_URL.rstrip("/") + "/api/collector/autoapprove"
        resp = _rest_call("POST", url, {"use_classify": (val == "on")})
        if not resp or not resp.get("ok"):
            _send_message(chat_id, "Ошибка: Collector недоступен")
            return
        flags = resp.get("flags") or {}
        _send_message(
            chat_id,
            (
                f"Классификация: {'включена' if (val == 'on') else 'выключена'}\n"
                f"Collector: use_classify={'on' if flags.get('use_classify') else 'off'}"
            )
        )
        return

    if cmd == "/news_to_approval":
        val = args.lower()
        if val not in ("on", "off"):
            _send_message(chat_id, "Использование: /news_to_approval on|off")
            return
        url = settings.COLLECTOR_URL.rstrip("/") + "/api/collector/autoapprove"
        resp = _rest_call("POST", url, {"send_news_to_approval": (val == "on")})
        if not resp or not resp.get("ok"):
            _send_message(chat_id, "Ошибка: Collector недоступен")
            return
        flags = resp.get("flags") or {}
        _send_message(
            chat_id,
            (
                f"Отправка новостей на апрув: {'включена' if (val == 'on') else 'выключена'}\n"
                f"Collector: send_news_to_approval={'on' if flags.get('send_news_to_approval') else 'off'}; auto_publish_news={'on' if flags.get('auto_publish_news') else 'off'}"
            )
        )
        return

    if cmd == "/others_to_approval":
        val = args.lower()
        if val not in ("on", "off"):
            _send_message(chat_id, "Использование: /others_to_approval on|off")
            return
        url = settings.COLLECTOR_URL.rstrip("/") + "/api/collector/autoapprove"
        resp = _rest_call("POST", url, {"send_others_to_approval": (val == "on")})
        if not resp or not resp.get("ok"):
            _send_message(chat_id, "Ошибка: Collector недоступен")
            return
        flags = resp.get("flags") or {}
        _send_message(
            chat_id,
            (
                f"Отправка прочих постов на апрув: {'включена' if (val == 'on') else 'выключена'}\n"
                f"Collector: send_others_to_approval={'on' if flags.get('send_others_to_approval') else 'off'}"
            )
        )
        return

    if cmd == "/digest_time":
        if not args:
            _send_message(chat_id, "Использование: /digest_time <HH:MM[,HH:MM ...]>")
            return
        # Парсим список времён, допускаем разделители запятая/пробел
        tokens = [t for t in args.replace(",", " ").split() if t]
        if not tokens or any(_parse_hhmm(t) is None for t in tokens):
            _send_message(chat_id, "Использование: /digest_time <HH:MM[,HH:MM ...]>")
            return
        # Нормализуем и сортируем по времени
        uniq = sorted({t for t in (tok.strip() for tok in tokens)}, key=lambda s: (int(s.split(":")[0]), int(s.split(":")[1])))
        cfg = _load_agg_config()
        cfg["schedules"] = uniq
        # Для обратной совместимости сохраним первый элемент в поле schedule
        cfg["schedule"] = uniq[0] if uniq else ""
        if _save_agg_config(cfg):
            _send_message(chat_id, f"Время(а) публикации установлено: {', '.join(uniq)}")
        else:
            _send_message(chat_id, "Не удалось сохранить конфигурацию агрегатора")
        return

    if cmd == "/digest_limit":
        try:
            n = int(args)
        except Exception:
            n = 0
        if n <= 0:
            _send_message(chat_id, "Использование: /digest_limit <N>")
            return
        cfg = _load_agg_config()
        cfg["limit"] = n
        if _save_agg_config(cfg):
            _send_message(chat_id, f"Лимит постов установлен: {n}")
        else:
            _send_message(chat_id, "Не удалось сохранить конфигурацию агрегатора")
        return

    if cmd == "/digest_reset":
        _send_message(chat_id, "Команда больше не используется: лимит на одну публикацию в день отключён")
        return

    if cmd == "/publish_now":
        if not settings.AGGREGATOR_URL:
            _send_message(chat_id, "Aggregator URL не задан, операция недоступна")
            return
        url = settings.AGGREGATOR_URL.rstrip("/") + "/api/aggregator/publish_now"
        resp = _rest_call("POST", url, {}, timeout=180)
        if resp and resp.get("ok"):
            _send_message(chat_id, "Публикация запущена")
        else:
            _send_message(chat_id, "Не удалось инициировать публикацию")
        return

    if cmd == "/status":
        try:
            # Собираем конфиг агрегатора и счётчики
            cfg = _load_agg_config()
            schedules = cfg.get("schedules") or ([cfg.get("schedule")] if cfg.get("schedule") else [])
            limit = cfg.get("limit")
            cfg_auto_news = cfg.get("auto_approve_news")
            cfg_auto_expert = cfg.get("auto_approve_expert")
            approved_count = None
            try:
                approved_count = len([f for f in os.listdir(settings.APPROVED_DIR) if f.endswith('.json')])
            except Exception:
                approved_count = None

            # Проверяем статусы сервисов через /health
            def _check(url: Optional[str]) -> Optional[Dict[str, Any]]:
                if not url:
                    return None
                try:
                    return _rest_call("GET", url.rstrip("/") + "/health")
                except Exception:
                    return None

            assistant_status = {"service": "assistant", "status": "ok"}
            collector_status = _check(settings.COLLECTOR_URL)
            aggregator_status = _check(settings.AGGREGATOR_URL)
            scheduler_status = _check(settings.SCHEDULER_URL)
            summarizer_status = _check(settings.SUMMARIZER_URL)
            publisher_status = _check(settings.PUBLISHER_URL)
            classifier_status = _check(settings.ASSISTANT_CLASSIFIER_URL)

            # Информация о вебхуке
            wh_info = _tg_api("getWebhookInfo", {}) or {}
            wh_result = wh_info.get("result", {}) if isinstance(wh_info, dict) else {}
            expected_wh = (settings.SERVICE_URL.rstrip("/") + "/telegram/webhook") if settings.SERVICE_URL else None
            curr_wh = wh_result.get("url")

            # Формируем ответ с разделами и группировкой (Markdown)
            lines: list[str] = []
            lines.append("*Настройки*")
            lines.append(f"admin_chat: {settings.ADMIN_CHAT_ID if settings.ADMIN_CHAT_ID is not None else 'not set'}")
            lines.append(f"bot_token: {'set' if bool(settings.BOT_TOKEN) else 'not set'}")
            lines.append(f"service_url: {settings.SERVICE_URL or 'not set'}")
            lines.append(f"webhook: current={curr_wh or 'none'}; expected={expected_wh or 'none'}")
            lines.append(f"collector_url: {settings.COLLECTOR_URL}")
            lines.append(f"aggregator_url: {settings.AGGREGATOR_URL or 'not set'}")
            lines.append(f"scheduler_url: {settings.SCHEDULER_URL or 'not set'}")
            lines.append(f"summarizer_url: {settings.SUMMARIZER_URL or 'not set'}")
            lines.append(f"publisher_url: {settings.PUBLISHER_URL or 'not set'}")
            lines.append(f"classifier_url: {settings.ASSISTANT_CLASSIFIER_URL or 'not set'}")
            lines.append(f"schedules: {', '.join(schedules) if schedules else 'not set'}")
            lines.append(f"limit: {limit}")
            lines.append(f"auto_approve_news: {'on' if cfg_auto_news else 'off'}")
            lines.append(f"auto_approve_expert: {'on' if cfg_auto_expert else 'off'}")
            lines.append(f"approved_count: {approved_count}")
            lines.append("")

            lines.append("*Статусы сервисов*")

            # Core группа
            lines.append("Assistant:")
            lines.append("status: ok")
            lines.append("")

            lines.append("Collector:")
            if not collector_status:
                lines.append("status: недоступен")
            else:
                lines.append(f"status: {collector_status.get('status') or 'unknown'}")
                lines.append(f"authorized: {collector_status.get('authorized')}")
                chs = collector_status.get('channels') or []
                lines.append(f"channels_count: {len(chs)}")
                q = collector_status.get('quiet') or {}
                lines.append(f"quiet: manual={q.get('manual')} schedule={q.get('schedule')} now={q.get('quiet_now')}")
                try:
                    ap = _rest_call("GET", settings.COLLECTOR_URL.rstrip("/") + "/api/collector/autoapprove")
                    if ap and ap.get("ok"):
                        flags = ap.get("flags") or {}
                        lines.append(
                            "autoapprove_flags: "
                            f"use_classify={'on' if flags.get('use_classify') else 'off'}, "
                            f"send_news_to_approval={'on' if flags.get('send_news_to_approval') else 'off'}, "
                            f"send_others_to_approval={'on' if flags.get('send_others_to_approval') else 'off'}, "
                            f"auto_publish_news={'on' if flags.get('auto_publish_news') else 'off'}"
                        )
                except Exception:
                    pass
            lines.append("")

            lines.append("Aggregator:")
            if not aggregator_status:
                lines.append("status: недоступен")
            else:
                st = aggregator_status.get("status") or "unknown"
                lines.append(f"status: {st}")
                lines.append(f"output_dir: {aggregator_status.get('output_dir')}")
            lines.append("")

            lines.append("Scheduler:")
            if not scheduler_status:
                lines.append("status: недоступен")
            else:
                lines.append(f"status: {scheduler_status.get('status') or 'unknown'}")
            lines.append("")

            # ML группа
            lines.append("Classifier:")
            if not classifier_status:
                lines.append("status: недоступен")
            else:
                lines.append(f"status: {classifier_status.get('status') or 'unknown'}")
            lines.append("")

            lines.append("Summarizer:")
            if not summarizer_status:
                lines.append("status: недоступен")
            else:
                lines.append(f"status: {summarizer_status.get('status') or 'unknown'}")
            lines.append("")

            # Publish группа
            lines.append("Publisher:")
            if not publisher_status:
                lines.append("status: недоступен")
            else:
                lines.append(f"status: {publisher_status.get('status') or 'unknown'}")
            lines.append("")

            _send_message(chat_id, "\n".join(lines))
        except Exception:
            logger.exception("/status handler failed")
            _send_message(chat_id, "Не удалось получить статус")
        return


# --- Webhook endpoint ---
@app.get("/telegram/webhook")
async def telegram_webhook_get():
    # Диагностика маршрутизации через публичный URL
    return JSONResponse({"ok": True, "mode": "diagnostic", "endpoint": "/telegram/webhook"})


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    try:
        logger.info("Webhook hit (POST)")
        # Проверка секрета вебхука (если задан)
        if settings.WEBHOOK_SECRET:
            hdr_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if hdr_secret != settings.WEBHOOK_SECRET:
                logger.warning("Webhook request with invalid secret; ignoring")
                return JSONResponse({"ok": True})

        upd = await request.json()
        try:
            keys = list(upd.keys()) if isinstance(upd, dict) else []
            logger.info(f"Webhook update keys: {keys}")
        except Exception:
            pass
    except Exception:
        logger.exception("Invalid JSON in webhook request")
        return JSONResponse({"ok": True})

    # 1) callback_query (кнопки модерации)
    cbq = upd.get("callback_query")
    if cbq:
        data = (cbq.get("data") or "").strip()
        message = cbq.get("message") or {}
        chat_id = ((message.get("chat") or {}).get("id"))
        msg_id = message.get("message_id")
        cb_id = cbq.get("id")

        logger.info(f"Callback received: data={data}, chat_id={chat_id}, message_id={msg_id}")

        # Авторизация Collector
        if data == "auth:start":
            _answer_callback(cb_id, "Запускаю авторизацию")
            # Сначала пробуем удалить сообщение; если не удалось — только тогда чистим клавиатуру
            if not _delete_message(chat_id, msg_id):
                _clear_markup(chat_id, msg_id)
            target_chat = settings.ADMIN_CHAT_ID or chat_id
            if settings.ADMIN_CHAT_ID and chat_id != settings.ADMIN_CHAT_ID:
                _send_message(settings.ADMIN_CHAT_ID, "Запрос авторизации: отправьте код из Telegram.")
            _start_auth_flow(target_chat)
            return JSONResponse({"ok": True})

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

        # По требованию: удаляем сообщение после нажатия; если удалить нельзя — убираем клавиатуру
        if not _delete_message(chat_id, msg_id):
            _clear_markup(chat_id, msg_id)

        return JSONResponse({"ok": True})

    # 2) text message с командами
    msg = upd.get("message") or {}
    if msg:
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        msg_id = msg.get("message_id")
        text = (msg.get("text") or "").strip()
        if text.startswith("/"):
            _handle_command(chat_id, msg_id, text)
        else:
            # Обрабатываем ввод для авторизации Collector
            _handle_auth_input(chat_id, text)

    return JSONResponse({"ok": True})