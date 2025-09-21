import asyncio
import os
import logging
from telethon import TelegramClient
from dotenv import load_dotenv
from telethon import __version__ as telethon_version
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError, FloodWaitError
from telethon import types as ttypes

# Подхватим .env из корня проекта
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_PATH = os.path.join(BASE_DIR, ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

# Логирование
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("collector.auth_login")

# Управление подробностью внутренних логов Telethon (например, DEBUG для детального трейсинга MTProto)
TELETHON_LOG_LEVEL = os.getenv("TELETHON_LOG_LEVEL")
if TELETHON_LOG_LEVEL:
    try:
        logging.getLogger("telethon").setLevel(TELETHON_LOG_LEVEL.upper())
        logger.info("Telethon internal log level set to %s", TELETHON_LOG_LEVEL.upper())
    except Exception:
        logger.exception("Failed to set Telethon log level")

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
# Поддерживаем обе переменные: PHONE_NUMBER (предпочтительно) и PHONE (обратная совместимость)
PHONE_NUMBER = os.getenv("PHONE_NUMBER") or os.getenv("PHONE")

DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

# Возможность форсировать отправку кода по SMS (по умолчанию выключено — используется код в приложении "Telegram")
FORCE_SMS = os.getenv("FORCE_SMS", "0") in ("1", "true", "True", "yes", "on")

# Авто-фоллбек на SMS, если код в приложении не пришёл
AUTO_FALLBACK_SMS = os.getenv("AUTO_FALLBACK_SMS", "0") in ("1", "true", "True", "yes", "on")
AUTO_FALLBACK_WAIT = int(os.getenv("AUTO_FALLBACK_WAIT", "75"))  # сек

SESSION_PATH = os.path.join(SESSIONS_DIR, "mtproto")  # Telethon добавит .session


def _mask_phone(phone: str | None) -> str:
    if not phone:
        return "<not set>"
    cleaned = phone.replace(" ", "")
    return f"***{cleaned[-3:]}" if len(cleaned) > 3 else "***"


def _mask_hash(h: str | None) -> str:
    if not h:
        return "<not set>"
    return f"len={len(h)}"


async def main():
    logger.info("Starting interactive Telethon auth (telethon=%s)", telethon_version)

    session_file = f"{SESSION_PATH}.session"
    exists = os.path.exists(session_file)
    size = os.path.getsize(session_file) if exists else 0

    if not API_ID or not API_HASH or not PHONE_NUMBER:
        logger.error("Missing required env vars: API_ID, API_HASH, and PHONE or PHONE_NUMBER")
        return

    logger.info(
        "Environment summary: API_ID=%s, API_HASH(%s), PHONE_NUMBER=%s, DATA_DIR=%s, SESSIONS_DIR=%s, SESSION_PATH=%s, FORCE_SMS=%s, AUTO_FALLBACK_SMS=%s, AUTO_FALLBACK_WAIT=%ss",
        API_ID,
        _mask_hash(API_HASH),
        _mask_phone(PHONE_NUMBER),
        DATA_DIR,
        SESSIONS_DIR,
        f"{SESSION_PATH}.session",
        FORCE_SMS,
        AUTO_FALLBACK_SMS,
        AUTO_FALLBACK_WAIT,
    )
    logger.info("Session file exists=%s size=%d bytes", exists, size)

    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    logger.debug("Connecting to Telegram...")
    await client.connect()
    logger.debug("Connected: is_connected=%s", client.is_connected())

    is_auth = await client.is_user_authorized()
    logger.info("Initial is_user_authorized=%s", is_auth)

    sent = None
    if not is_auth:
        try:
            logger.info("Requesting login code delivery via Telegram app (in-app). FORCE_SMS=%s", FORCE_SMS)
            sent = await client.send_code_request(PHONE_NUMBER, force_sms=FORCE_SMS)
            # Логируем детали ответа сервера по отправке кода
            try:
                stype = type(sent.type).__name__ if getattr(sent, 'type', None) is not None else None
                ntype = type(sent.next_type).__name__ if getattr(sent, 'next_type', None) is not None else None
                logger.info(
                    "Code request sent. server_sent.type=%s next_type=%s timeout=%s. Check the 'Telegram' service chat in your Telegram app%s",
                    stype,
                    ntype,
                    getattr(sent, 'timeout', None),
                    " [forced SMS]" if FORCE_SMS else "",
                )
            except Exception:
                logger.debug("Could not introspect SentCode object", exc_info=True)
        except FloodWaitError as e:
            logger.error("Too many attempts (FLOOD_WAIT). Retry after %s seconds.", e.seconds)
            return
        except Exception as e:
            logger.exception("Failed to send code: %s", e)
            return

        # Авто-фоллбек на SMS, если включён и сервер изначально предложил in-app код
        if (not FORCE_SMS) and AUTO_FALLBACK_SMS and sent and isinstance(getattr(sent, 'type', None), ttypes.auth.SentCodeTypeApp):
            logger.warning(
                "No in-app code observed yet? Will fallback to SMS automatically after %s seconds (set AUTO_FALLBACK_WAIT).",
                AUTO_FALLBACK_WAIT,
            )
            try:
                await asyncio.sleep(AUTO_FALLBACK_WAIT)
                logger.warning("Triggering SMS fallback with force_sms=True ...")
                sent2 = await client.send_code_request(PHONE_NUMBER, force_sms=True)
                stype2 = type(sent2.type).__name__ if getattr(sent2, 'type', None) is not None else None
                logger.info("Fallback code request sent. server_sent.type=%s timeout=%s [forced SMS]", stype2, getattr(sent2, 'timeout', None))
            except FloodWaitError as e:
                logger.error("FLOOD_WAIT on SMS fallback. Retry after %s seconds.", e.seconds)
                return
            except Exception:
                logger.exception("Failed during SMS fallback send_code_request")
                return

        code = input("Enter the code you received: ").strip()
        try:
            logger.debug("Signing in with code...")
            await client.sign_in(PHONE_NUMBER, code)
        except SessionPasswordNeededError:
            password = input("Two-step verification enabled. Enter your password: ").strip()
            try:
                logger.debug("Signing in with 2FA password...")
                await client.sign_in(password=password)
            except Exception as e:
                logger.exception("Password sign-in failed: %s", e)
                return
        except PhoneCodeInvalidError:
            logger.error("Invalid code. Please retry.")
            return
        except PhoneCodeExpiredError:
            logger.error("Code expired. Please retry.")
            return
        except Exception as e:
            logger.exception("Sign in failed: %s", e)
            return

    try:
        me = await client.get_me()
        logger.info(
            "Authorized as: id=%s username=%s first_name=%s",
            getattr(me, 'id', None),
            getattr(me, 'username', None),
            getattr(me, 'first_name', None),
        )
    except Exception as e:
        logger.exception("Failed to fetch account info: %s", e)

    # Уточним состояние файла сессии после авторизации
    exists_after = os.path.exists(session_file)
    size_after = os.path.getsize(session_file) if exists_after else 0
    logger.info("Session file after auth exists=%s size=%d bytes", exists_after, size_after)

    await client.disconnect()
    logger.debug("Disconnected")


if __name__ == "__main__":
    asyncio.run(main())