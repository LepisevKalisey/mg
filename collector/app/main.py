from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Dict, Optional, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import Channel

from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command

# Load .env for local runs
load_dotenv()

# ----- Config -----
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_DIR = os.getenv("SESSION_DIR", "sessions")
SESSION_NAME = os.getenv("SESSION_NAME", "mtproto")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ALLOWED_TG_IDS = {int(x) for x in (os.getenv("ALLOWED_TG_IDS", "").split(",") if x.strip())}
ROLE_ADMINS = {int(x) for x in (os.getenv("ROLE_ADMINS", "").split(",") if x.strip())}
ALLOWED_IDS = {i for i in (ALLOWED_TG_IDS | ROLE_ADMINS) if i}

# Ensure session dir exists
Path(SESSION_DIR).mkdir(parents=True, exist_ok=True)
SESSION_PATH = str(Path(SESSION_DIR) / f"{SESSION_NAME}.session")

# ----- Globals -----
app = FastAPI(title="MG Collector", version="0.2.0")

_telethon_client: Optional[TelegramClient] = None
_phone_hashes: Dict[str, str] = {}  # phone -> phone_code_hash

# Aiogram bot (long polling) for admin commands
bot: Optional[Bot] = None
dp: Optional[Dispatcher] = None
router = Router()
_bot_task: Optional[asyncio.Task] = None


def require_api_creds():
    if not API_ID or not API_HASH:
        raise HTTPException(status_code=400, detail="API_ID/API_HASH не заданы в окружении (.env)")


def get_client() -> TelegramClient:
    global _telethon_client
    require_api_creds()
    if _telethon_client is None:
        _telethon_client = TelegramClient(SESSION_PATH, int(API_ID), API_HASH)
    return _telethon_client


# ----- Pydantic models -----
class SendCodeRequest(BaseModel):
    phone: str


class SignInRequest(BaseModel):
    phone: str
    code: str


class TwoFARequest(BaseModel):
    password: str


# ----- FastAPI endpoints -----
@app.get("/healthz")
async def healthz():
    client = get_client()
    await client.connect()
    authorized = await client.is_user_authorized()
    me = None
    if authorized:
        me = await client.get_me()
        me = {"id": me.id, "username": me.username, "first_name": me.first_name}
    return {
        "status": "ok",
        "service": "collector",
        "authorized": authorized,
        "me": me,
    }


@app.get("/auth/status")
async def auth_status():
    client = get_client()
    await client.connect()
    authorized = await client.is_user_authorized()
    return {"authorized": authorized}


@app.post("/auth/send_code")
async def auth_send_code(req: SendCodeRequest):
    client = get_client()
    await client.connect()
    try:
        sent = await client.send_code_request(req.phone)
        _phone_hashes[req.phone] = sent.phone_code_hash
        return {"status": "code_sent"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка отправки кода: {e}")


@app.post("/auth/sign_in")
async def auth_sign_in(req: SignInRequest):
    client = get_client()
    await client.connect()
    if req.phone not in _phone_hashes:
        raise HTTPException(status_code=400, detail="Сначала вызовите /auth/send_code")
    try:
        await client.sign_in(phone=req.phone, code=req.code, phone_code_hash=_phone_hashes[req.phone])
        return {"status": "signed_in"}
    except SessionPasswordNeededError:
        return {"status": "2fa_required"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка входа: {e}")


@app.post("/auth/2fa")
async def auth_2fa(req: TwoFARequest):
    client = get_client()
    await client.connect()
    try:
        await client.sign_in(password=req.password)
        return {"status": "signed_in"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка 2FA: {e}")


@app.post("/auth/logout")
async def auth_logout():
    client = get_client()
    await client.connect()
    try:
        await client.log_out()
        return {"status": "logged_out"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка выхода: {e}")


# ----- Aiogram bot: /channels -----
@router.message(Command("channels"))
async def cmd_channels(message: types.Message):
    user_id = message.from_user.id if message.from_user else 0
    if ALLOWED_IDS and user_id not in ALLOWED_IDS:
        await message.reply("Доступ запрещён")
        return

    client = get_client()
    await client.connect()
    if not await client.is_user_authorized():
        await message.reply("Аккаунт MTProto не авторизован. Сначала выполните авторизацию через REST: /auth/send_code → /auth/sign_in")
        return

    channels: List[str] = []
    async for dialog in client.iter_dialogs():
        ent = dialog.entity
        if isinstance(ent, Channel) and getattr(ent, "broadcast", False):
            uname = f"@{ent.username}" if ent.username else f"id={ent.id}"
            title = ent.title or "(без названия)"
            channels.append(f"• {title} ({uname})")

    if not channels:
        await message.reply("Каналы не найдены")
        return

    # Telegram имеет лимит на длину сообщения, отправим по частям
    text = "Список каналов, на которые подписан аккаунт:\n" + "\n".join(channels)
    for chunk_start in range(0, len(text), 3500):
        await message.reply(text[chunk_start:chunk_start + 3500])


@app.on_event("startup")
async def on_startup():
    global bot, dp, _bot_task
    # Lazy init Telethon connection (do nothing if creds missing will be validated on request)
    # Start bot polling if token provided
    if not BOT_TOKEN:
        print("[COLLECTOR] BOT_TOKEN не задан — бот не будет запущен")
    else:
        bot = Bot(BOT_TOKEN)
        dp = Dispatcher()
        dp.include_router(router)
        _bot_task = asyncio.create_task(dp.start_polling(bot))
        print("[COLLECTOR] Bot polling started")


@app.on_event("shutdown")
async def on_shutdown():
    global bot, dp, _bot_task, _telethon_client
    if _bot_task and not _bot_task.done():
        _bot_task.cancel()
        try:
            await _bot_task
        except Exception:
            pass
    if bot:
        await bot.session.close()
    if _telethon_client:
        try:
            await _telethon_client.disconnect()
        except Exception:
            pass