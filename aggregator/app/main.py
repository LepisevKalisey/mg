from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from aiogram import Bot
from dotenv import load_dotenv

# Load .env for local runs
load_dotenv()


# ----- Config -----
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
PUBLISH_CHANNEL_ID = int(os.getenv("PUBLISH_CHANNEL_ID", "0"))
MONITOR_CHANNELS = [c.strip() for c in os.getenv("MONITOR_CHANNELS", "").split(",") if c.strip()]
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_API_BASE = os.getenv("LLM_API_BASE", "")
SUMMARY_SCHEDULE_CRON = os.getenv("SUMMARY_SCHEDULE_CRON", "0 5 * * *")  # default 05:00 UTC

API_ID = os.getenv("API_ID")  # Telethon optional for future
API_HASH = os.getenv("API_HASH")


class Post(BaseModel):
    title: Optional[str] = None
    url: Optional[HttpUrl | str] = None
    text: Optional[str] = None


class PublishRequest(BaseModel):
    posts: List[Post] = []


app = FastAPI(title="MG Aggregator", version="0.1.0")

# Aiogram Bot (created lazily)
bot: Optional[Bot] = None
scheduler: Optional[AsyncIOScheduler] = None


@app.on_event("startup")
async def on_startup():
    global bot, scheduler
    # Init bot
    if not BOT_TOKEN:
        print("[WARN] BOT_TOKEN is not set. Publishing will be disabled.")
    else:
        bot = Bot(BOT_TOKEN)

    # Init scheduler
    scheduler = AsyncIOScheduler(timezone=timezone.utc)
    try:
        trigger = CronTrigger.from_crontab(SUMMARY_SCHEDULE_CRON)
    except Exception as e:
        print(f"[WARN] Invalid SUMMARY_SCHEDULE_CRON='{SUMMARY_SCHEDULE_CRON}': {e}. Fallback to '0 5 * * *'")
        trigger = CronTrigger.from_crontab("0 5 * * *")

    scheduler.add_job(job_publish_daily_summary, trigger, name="daily_summary")
    scheduler.start()
    print("[INIT] Aggregator started. Scheduler running.")


@app.on_event("shutdown")
async def on_shutdown():
    global bot, scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
    if bot:
        await bot.session.close()


@app.get("/healthz")
def healthz():
    return {
        "status": "ok",
        "service": "aggregator",
        "time": datetime.now(timezone.utc).isoformat(),
        "monitor_channels": MONITOR_CHANNELS,
        "schedule_cron": SUMMARY_SCHEDULE_CRON,
    }


@app.post("/publish_now")
async def publish_now(req: Optional[PublishRequest] = None):
    posts = req.posts if req and req.posts else await fetch_recent_posts()
    if not posts:
        return {"status": "no_posts", "message": "Нет данных для публикации. Добавьте посты или настройте сбор."}

    message_text = await build_summary_message(posts)

    if not BOT_TOKEN or not PUBLISH_CHANNEL_ID:
        raise HTTPException(status_code=400, detail="BOT_TOKEN или PUBLISH_CHANNEL_ID не настроены")

    await send_to_channel(message_text)
    return {"status": "sent", "count": len(posts)}


@app.post("/ingest_and_publish")
async def ingest_and_publish(req: PublishRequest):
    if not req.posts:
        raise HTTPException(status_code=400, detail="Нет постов для публикации")
    message_text = await build_summary_message(req.posts)
    await send_to_channel(message_text)
    return {"status": "sent", "count": len(req.posts)}


# ----- Core logic -----
async def fetch_recent_posts() -> List[Post]:
    # Minimal MVP: no Telethon yet. We return empty to indicate collector is not implemented.
    # Future: if API_ID/API_HASH provided and MTProto session exists, use Telethon to pull last 24h posts from MONITOR_CHANNELS.
    return []


def build_prompt(posts: List[Post]) -> str:
    # Instruction for Gemini: create concise hooky summaries for each item
    items = []
    for i, p in enumerate(posts, start=1):
        title = p.title or (p.text or "").strip().split("\n")[0][:120]
        text = (p.text or "").strip()
        url = p.url or ""
        items.append(f"[{i}] Title: {title}\nURL: {url}\nText: {text}")
    items_str = "\n\n".join(items)
    return (
        "Ты — редактор новостной рассылки. Для каждого элемента составь: "
        "1) Краткий заголовок (до 12 слов), 2) Короткий цепляющий саммари (1–2 предложения). "
        "Не добавляй лишних символов. Ответ в формате списком по пунктам:\n\n"
        f"Входные данные:\n{items_str}\n\n"
        "Формат ответа для каждого пункта:\n"
        "- Заголовок: <краткий заголовок>\n"
        "- Саммари: <1-2 предложения>\n"
    )


async def call_gemini(prompt: str) -> str:
    if not LLM_API_BASE or not LLM_API_KEY:
        # Fallback: simple echo summarization
        return "Сводка недоступна: LLM не настроен."

    params = {"key": LLM_API_KEY}
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(LLM_API_BASE, params=params, json=payload)
            resp.raise_for_status()
            data = resp.json()
            # Extract text: candidates[0].content.parts[0].text
            candidates = data.get("candidates") or []
            if candidates:
                content = candidates[0].get("content") or {}
                parts = content.get("parts") or []
                if parts and isinstance(parts, list) and "text" in parts[0]:
                    return parts[0]["text"].strip()
            # Fallback if structure differs
            return str(data)[:2000]
        except httpx.HTTPError as e:
            return f"Ошибка LLM: {e}"


def render_message(posts: List[Post], llm_text: str) -> str:
    # Combine LLM output with links. We assume LLM produced items in order.
    lines = [l for l in llm_text.splitlines() if l.strip()]
    result_lines: List[str] = []
    idx = 0
    for p in posts:
        # try to find a block (two consecutive lines starting with markers)
        title_line = None
        summary_line = None
        while idx < len(lines) and (title_line is None or summary_line is None):
            ln = lines[idx].strip()
            if title_line is None and (ln.lower().startswith("- заголовок:") or ln.lower().startswith("заголовок:")):
                title_line = ln.split(":", 1)[-1].strip()
            elif summary_line is None and (ln.lower().startswith("- саммари:") or ln.lower().startswith("саммари:")):
                summary_line = ln.split(":", 1)[-1].strip()
            idx += 1
        title = title_line or (p.title or (p.text or "").strip().split("\n")[0][:80] or "Новость")
        url = p.url or ""
        if url:
            result_lines.append(f"<a href=\"{url}\">{escape_html(title)}</a>")
        else:
            result_lines.append(escape_html(title))
        if summary_line:
            result_lines.append(escape_html(summary_line))
        result_lines.append("")
    return "\n".join(result_lines).strip()


def escape_html(text: str) -> str:
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


async def build_summary_message(posts: List[Post]) -> str:
    prompt = build_prompt(posts)
    llm_text = await call_gemini(prompt)
    return render_message(posts, llm_text)


async def send_to_channel(message_text: str):
    if not bot:
        raise RuntimeError("Bot is not initialized")
    await bot.send_message(chat_id=PUBLISH_CHANNEL_ID, text=message_text, parse_mode="HTML", disable_web_page_preview=True)


async def job_publish_daily_summary():
    try:
        posts = await fetch_recent_posts()
        if not posts:
            print("[JOB] Нет постов для ежедневной сводки — пропуск")
            return
        message_text = await build_summary_message(posts)
        await send_to_channel(message_text)
        print("[JOB] Ежедневная сводка отправлена")
    except Exception as e:
        print(f"[JOB][ERROR] {e}")