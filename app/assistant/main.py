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
            logger.warning(f"setWebhook failed: {set_res}")
    else:
        logger.info(f"Webhook already set to: {curr_url}")


@app.get("/health")
async def health():
    # Покажем текущие параметры и url вебхука
    wh_info = _tg_api("getWebhookInfo", {}) or {}
    result = wh_info.get("result", {}) if isinstance(wh_info, dict) else {}
    curr_url = result.get("url")
    return JSONResponse({
        "service": "assistant",
        "status": "ok",
        "data_dirs": {
            "pending": settings.PENDING_DIR,
            "approved": settings.APPROVED_DIR,
        },
        "webhook": {
            "expected": (settings.SERVICE_URL.rstrip("/") + "/telegram/webhook") if settings.SERVICE_URL else None,
            "current": curr_url,
            "pending_update_count": result.get("pending_update_count"),
            "ip_address": result.get("ip_address"),
            "last_error_date": result.get("last_error_date"),
            "last_error_message": result.get("last_error_message"),
            "max_connections": result.get("max_connections"),
            "allowed_updates": result.get("allowed_updates"),
        }
    })


@app.get("/debug/webhook-info")
async def debug_webhook_info():
    info = _tg_api("getWebhookInfo", {}) or {}
    return JSONResponse(info)


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


def _delete_message(chat_id: Optional[int], message_id: Optional[int]) -> None:
    if not chat_id or not message_id:
        return
    _tg_api("deleteMessage", {"chat_id": chat_id, "message_id": message_id})


def _clear_markup(chat_id: Optional[int], message_id: Optional[int]) -> None:
    if not chat_id or not message_id:
        return
    _tg_api("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id, "reply_markup": {}})


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
        pass
    phone_line = f"\nНомер: {phone_hint}" if phone_hint else ""

    # Если кнопка нажата не из админ-чата, подсказка
    if settings.ADMIN_CHAT_ID and chat_id != settings.ADMIN_CHAT_ID:
        _send_message(chat_id, "Запрос авторизации принят. Я написал инструкции в админ-чат.")
        _send_message(settings.ADMIN_CHAT_ID, "Запрос авторизации: отправьте код из Telegram." + phone_line)
    else:
        _send_message(target_chat, "Запрос авторизации: отправьте код из Telegram." + phone_line)

    res = _rest_call("POST", settings.COLLECTOR_URL + "/api/collector/auth/start", {"phone": None, "chat_id": target_chat}) or {}
    if res.get("ok"):
        _AUTH_WAIT[target_chat] = "code"
        _send_message(target_chat, "Код отправлен. Пришлите его в ответ.")
    else:
        _send_message(target_chat, "Не удалось инициировать авторизацию. Проверьте номер телефона в настройках Collector.")


def _handle_auth_input(chat_id: int, text: str) -> None:
    mode = _AUTH_WAIT.get(chat_id)
    if not mode:
        return
    if settings.ADMIN_CHAT_ID is not None and chat_id != settings.ADMIN_CHAT_ID:
        return
    if mode == "code":
        url = settings.COLLECTOR_URL.rstrip("/") + "/api/collector/auth/code"
        resp = _rest_call("POST", url, {"code": text})
        if not resp:
            _send_message(chat_id, "Collector недоступен")
            return
        result = resp.get("result") or ""
        st = resp.get("status") or {}
        if result == "ok" and (resp.get("ok") or st.get("authorized")):
            _AUTH_WAIT.pop(chat_id, None)
            _send_message(chat_id, "Авторизация выполнена")
        elif result == "password_required" or st.get("await_password"):
            _AUTH_WAIT[chat_id] = "password"
            _send_message(chat_id, "Требуется пароль 2FA. Введите пароль")
        elif result == "error:invalid_code":
            _send_message(chat_id, "Неверный код. Пожалуйста, проверьте и введите код ещё раз")
        else:
            _send_message(chat_id, f"Ошибка: {result or 'неизвестная'}. Попробуйте снова")
    elif mode == "password":
        url = settings.COLLECTOR_URL.rstrip("/") + "/api/collector/auth/password"
        resp = _rest_call("POST", url, {"password": text})
        if not resp:
            _send_message(chat_id, "Collector недоступен")
            return
        st = resp.get("status") or {}
        if resp.get("ok") and (st.get("authorized")):
            _AUTH_WAIT.pop(chat_id, None)
            _send_message(chat_id, "Авторизация выполнена")
        else:
            _send_message(chat_id, "Пароль не принят. Попробуйте снова")

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


# --- HTTP helper для REST сервисов ---

def _rest_call(method: str, url: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 20) -> Optional[Dict[str, Any]]:
    try:
        data = None
        headers = {"Content-Type": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(url, data=data, headers=headers, method=method.upper())
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            txt = resp.read().decode("utf-8")
            return json.loads(txt)
    except HTTPError as he:
        try:
            err_body = he.read().decode("utf-8")
        except Exception:
            err_body = str(he)
        logger.warning(f"REST {method} {url} failed: {he.code} {err_body}")
    except Exception:
        logger.warning(f"REST {method} {url} failed", exc_info=True)
    return None


# --- Конфиг агрегатора ---

def _load_agg_config() -> Dict[str, Any]:
    try:
        if os.path.isfile(settings.AGGREGATOR_CONFIG_PATH):
            with open(settings.AGGREGATOR_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception:
        logger.exception("Failed to read aggregator config")
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


# --- Команды бота ---

def _help_text() -> str:
    return (
        "Доступные команды:\n"
        "\n"
        "Источники (Collector):\n"
        "/add_source <@channel|t.me/link> — добавить источник\n"
        "/remove_source <@channel|t.me/link> — удалить источник\n"
        "/list_sources — показать текущий список\n"
        "\n"
        "Тихие часы (уведомления редакторам без звука):\n"
        "/quiet on|off — включить/выключить тихий режим\n"
        "/quiet_schedule <HH:MM-HH:MM|off> — задать интервал или отключить\n"
        "\n"
        "Дайджест (Aggregator):\n"
        "/digest_time <HH:MM> — время ежедневной публикации\n"
        "/digest_limit <N> — лимит постов в выпуске\n"
        "/publish_now — принудительно опубликовать сейчас\n"
        "\n"
        "/status — статус микросервисов\n"
        "/help — эта справка\n"
    )


def _validate_hhmm(s: str) -> bool:
    parts = s.split(":")
    if len(parts) != 2:
        return False
    try:
        hh = int(parts[0])
        mm = int(parts[1])
        return 0 <= hh <= 23 and 0 <= mm <= 59
    except Exception:
        return False


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
        resp = _rest_call("POST", url, {})
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
                    lines.append(f"approved_count: {approved_count if approved_count is not None else 'n/a'}")
                    lines.append(f"approved_dir: {agg_status.get('approved_dir')}")
                    lines.append(f"output_dir: {agg_status.get('output_dir')}")
                lines.append(f"schedule: {schedule or 'not set'}")
                lines.append(f"limit: {limit or 'default'}")
                lines.append(f"last_run: {last_run_date or 'never'}")
            else:
                lines.append("status: URL не задан")

            _send_message(chat_id, "\n".join(lines))
        except Exception:
            logger.exception("/status handler failed")
        return

    # Неизвестная команда
    _send_message(chat_id, "Неизвестная команда. Введите /help")


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

        # По требованию: удаляем сообщение после нажатия
        _delete_message(chat_id, msg_id)
        # На случай отсутствия прав на удаление — уберём клавиатуру
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
            # Обрабатываем ввод кода/пароля для авторизации Collector
            _handle_auth_input(chat_id, text)
        return JSONResponse({"ok": True})

    # Остальные типы апдейтов игнорируем
    return JSONResponse({"ok": True})


@app.on_event("shutdown")
async def on_shutdown():
    global _scheduler_task
    if _scheduler_task:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except Exception:
            pass