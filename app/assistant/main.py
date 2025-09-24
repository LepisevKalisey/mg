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
    while True:
        try:
            cfg = _load_agg_config()
            sched = (cfg.get("schedule") or "").strip()
            parsed = _parse_hhmm(sched) if sched else None
            if parsed and settings.AGGREGATOR_URL:
                h, m = parsed
                now = datetime.now()
                target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                last_date = cfg.get("last_run_date")
                # Если время наступило и сегодня ещё не запускали — запускаем
                if now >= target and last_date != _now_date_str():
                    limit = cfg.get("limit")
                    url = settings.AGGREGATOR_URL.rstrip("/") + "/api/aggregator/publish_now"
                    if isinstance(limit, int) and limit > 0:
                        url = f"{url}?limit={int(limit)}"
                    logger.info(f"Scheduled publish trigger: {url}")
                    resp = _rest_call("POST", url, {}) or {}
                    if resp.get("ok") and resp.get("result") == "ok" and resp.get("published"):
                        cfg["last_run_date"] = _now_date_str()
                        _save_agg_config(cfg)
                        logger.info("Scheduled publish finished successfully")
                    else:
                        logger.warning(f"Scheduled publish failed or not published: resp={resp}")
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
        logger.info(
            "Scheduler config: schedule=%s, limit=%s, aggregator_url=%s",
            cfg.get("schedule"), cfg.get("limit"), ("set" if settings.AGGREGATOR_URL else "not set"),
        )
    except Exception:
        logger.warning("Failed to load scheduler config on startup")

    # Запускаем фоновый планировщик публикаций
    global _scheduler_task
    if _scheduler_task is None:
        _scheduler_task = asyncio.create_task(_digest_scheduler())

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
            "schedule": cfg.get("schedule"),
            "limit": cfg.get("limit"),
            "last_run_date": cfg.get("last_run_date"),
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
        return True
    except Exception:
        logger.exception("Approve failed")
        return False


def _reject(filename: str) -> bool:
    try:
        src = os.path.join(settings.PENDING_DIR, filename)
        if not os.path.exists(src):
            return False
        os.remove(src)
        logger.info(f"Rejected: {filename}")
        return True
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
        with open(settings.AGGREGATOR_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        logger.exception("Failed to write aggregator config")
        return False


def _help_text() -> str:
    lines = [
        "Доступные команды:",
        "/help — показать справку",
        "/add_source <@channel|t.me/link> — добавить источник",
        "/remove_source <@channel|t.me/link> — удалить источник",
        "/list_sources — показать список источников",
        "/quiet on|off — включить/выключить тихий режим",
        "/quiet_schedule <HH:MM-HH:MM|off> — настроить тихие часы",
        "/digest_time <HH:MM> — установить время ежедневной публикации",
        "/digest_limit <N> — ограничить число постов в дайджесте",
        "/publish_now — запустить публикацию сейчас",
        "/status — показать статусы сервисов",
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

    if cmd == "/digest_time":
        if not args or not _validate_hhmm(args):
            _send_message(chat_id, "Использование: /digest_time <HH:MM>")
            return
        cfg = _load_agg_config()
        cfg["schedule"] = args
        if _save_agg_config(cfg):
            _send_message(chat_id, f"Время публикации установлено: {args}")
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

    if cmd == "/publish_now":
        if not settings.AGGREGATOR_URL:
            _send_message(chat_id, "Aggregator URL не задан, операция недоступна")
            return
        url = settings.AGGREGATOR_URL.rstrip("/") + "/api/aggregator/publish_now"
        resp = _rest_call("POST", url, {}, timeout=180)
        if resp and resp.get("ok"):
            _send_message(chat_id, "Публикация запущена")
            try:
                if resp.get("published"):
                    cfg = _load_agg_config()
                    cfg["last_run_date"] = _now_date_str()
                    _save_agg_config(cfg)
            except Exception:
                logger.warning("Failed to update last_run_date after /publish_now")
        else:
            _send_message(chat_id, "Не удалось инициировать публикацию")
        return

    if cmd == "/status":
        try:
            # Собираем статусы сервисов
            self_status = {"service": "assistant", "status": "ok"}
            col_status = None
            try:
                col_status = _rest_call("GET", settings.COLLECTOR_URL.rstrip("/") + "/health")
            except Exception:
                col_status = None
            agg_status = None
            if settings.AGGREGATOR_URL:
                try:
                    agg_status = _rest_call("GET", settings.AGGREGATOR_URL.rstrip("/") + "/health")
                except Exception:
                    agg_status = None

            # Конфигурация агрегатора (расписание и лимиты)
            cfg = _load_agg_config()
            schedule = cfg.get("schedule")
            limit = cfg.get("limit")
            last_run_date = cfg.get("last_run_date")

            # Подсчёт количества файлов в approved
            approved_count = None
            try:
                approved_count = len([f for f in os.listdir(settings.APPROVED_DIR) if f.endswith('.json')])
            except Exception:
                approved_count = None

            lines: list[str] = []
            lines.append("Assistant:\n" + "status: ok")
            # Информация о вебхуке
            wh_info = _tg_api("getWebhookInfo", {}) or {}
            result = wh_info.get("result", {}) if isinstance(wh_info, dict) else {}
            expected_wh = (settings.SERVICE_URL.rstrip("/") + "/telegram/webhook") if settings.SERVICE_URL else None
            curr_wh = result.get("url")
            lines.append(f"webhook: current={curr_wh or 'none'}; expected={expected_wh or 'none'}")
            lines.append(f"admin_chat: {settings.ADMIN_CHAT_ID if settings.ADMIN_CHAT_ID is not None else 'not set'}")
            lines.append(f"bot_token: {'set' if bool(settings.BOT_TOKEN) else 'not set'}")
            lines.append(f"collector_url: {settings.COLLECTOR_URL}")
            lines.append(f"aggregator_url: {settings.AGGREGATOR_URL or 'not set'}")
            lines.append("")

            # Collector
            lines.append("Collector:")
            if not col_status:
                lines.append("status: недоступен")
            else:
                st = col_status.get("status") or "unknown"
                authorized = col_status.get("authorized")
                channels = col_status.get("channels") or []
                quiet = (col_status.get("quiet") or {})
                lines.append(f"status: {st}")
                lines.append(f"authorized: {authorized}")
                lines.append(f"channels_count: {len(channels)}")
                lines.append(f"quiet: manual={quiet.get('manual')} schedule={quiet.get('schedule')} now={quiet.get('quiet_now')}")
            lines.append("")

            # Aggregator
            lines.append("Aggregator:")
            if settings.AGGREGATOR_URL:
                if not agg_status:
                    lines.append("status: недоступен")
                else:
                    st = agg_status.get("status") or "unknown"
                    lines.append(f"status: {st}")
                    lines.append(f"output_dir: {agg_status.get('output_dir')}")
            else:
                lines.append("status: не сконфигурирован (AGGREGATOR_URL not set)")
            lines.append("")

            # Aggregator config
            lines.append("Aggregator config:")
            lines.append(f"schedule: {schedule}")
            lines.append(f"limit: {limit}")
            lines.append(f"last_run_date: {last_run_date}")
            lines.append(f"approved_count: {approved_count}")

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


@app.on_event("shutdown")
async def on_shutdown():
    global _scheduler_task
    if _scheduler_task is not None:
        try:
            _scheduler_task.cancel()
        except Exception:
            pass
    try:
        await asyncio.sleep(0.05)
    except Exception:
        pass