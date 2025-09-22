import os
import json
import glob
import logging
from typing import List, Dict, Any, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse

# Added: urllib for Telegram Bot API publishing
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from .config import settings
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("aggregator.main")

app = FastAPI(title="MediaGenerator Aggregator", version="0.1.0")


def _read_approved(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    pattern = os.path.join(settings.APPROVED_DIR, "*.json")
    files = sorted(glob.glob(pattern))
    if limit:
        files = files[:limit]
    items: List[Dict[str, Any]] = []
    for p in files:
        try:
            with open(p, "r", encoding="utf-8") as f:
                payload = json.load(f)
            items.append({"path": p, "payload": payload})
        except Exception:
            logger.exception("Failed to read %s", p)
    return items


def _compose_prompt(items: List[Dict[str, Any]], lang: str) -> str:
    # Строим компактный промпт для модели: заголовок канала + ссылка + текст
    lines: List[str] = [
        "Ты — помощник, который делает краткое, ёмкое саммари новостей на русском языке.",
        "Сжато, по пунктам, с заголовками. Укажи источники (имя канала и ссылку).",
    ]
    for it in items:
        p = it["payload"]
        title = p.get("channel_title") or p.get("channel_name") or "Канал"
        username = p.get("channel_username")
        msg_id = p.get("message_id")
        url = f"https://t.me/{username}/{msg_id}" if username and msg_id else ""
        text = p.get("text") or (p.get("media") or {}).get("caption") or ""
        # Обрезаем слишком длинные
        if text and len(text) > 4000:
            text = text[:4000] + "…"
        block = f"\n### {title}\n{url}\n{text}".strip()
        lines.append(block)
    lines.append("\nВыведи результат в формате: \n- [Заголовок] Краткое содержание (Источник: ИмяКанала — ссылка)")
    return "\n".join(lines)


def _use_gemini(prompt: str) -> str:
    try:
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model_name = "gemini-1.5-flash"
        start = time.perf_counter()
        logger.info(f"Gemini request: model={model_name} prompt_len={len(prompt)}")
        model = genai.GenerativeModel(model_name)
        resp = model.generate_content(prompt)
        duration_ms = int((time.perf_counter() - start) * 1000)
        text = (resp.text or "").strip()
        logger.info(f"Gemini response: ok={bool(text)} text_len={len(text)} duration_ms={duration_ms}")
        return text
    except Exception as e:
        logger.exception("Gemini call failed: %s", e)
        return ""


def _fallback_summary(items: List[Dict[str, Any]], lang: str) -> str:
    # Простой фолбэк без ML: собираем список пунктов из текстов
    # Формат: - [Канал] первая строка текста… (Источник: @username/ID)
    lines: List[str] = []
    for it in items:
        p = it["payload"]
        title = p.get("channel_title") or p.get("channel_name") or "Канал"
        username = p.get("channel_username")
        msg_id = p.get("message_id")
        url = f"https://t.me/{username}/{msg_id}" if username and msg_id else ""
        text = p.get("text") or (p.get("media") or {}).get("caption") or ""
        first_line = (text or "").splitlines()[0].strip()
        if len(first_line) > 200:
            first_line = first_line[:200] + "…"
        src = f"Источник: {title} — {url}" if url else f"Источник: {title}"
        lines.append(f"- [{title}] {first_line} ({src})")
    header = "Дайджест (фолбэк):"
    return "\n".join([header] + lines)


@app.get("/health")
def health():
    return JSONResponse({
        "ok": True,
        "status": "ok",
        "service": "aggregator",
        "approved_dir": settings.APPROVED_DIR,
        "output_dir": settings.OUTPUT_DIR,
    })


@app.post("/api/aggregator/run")
def run_aggregation(limit: Optional[int] = None):
    items = _read_approved(limit or settings.BATCH_LIMIT)
    if not items:
        return JSONResponse({"ok": True, "result": "empty", "summary": ""})

    logger.info(f"Run aggregation: items={len(items)}")
    prompt = _compose_prompt(items, settings.SUMMARY_LANGUAGE)
    summary = _use_gemini(prompt)
    if not summary:
        logger.error("Gemini returned empty summary; aborting aggregation")
        return JSONResponse({"ok": False, "result": "gemini_failed", "error": "empty_summary"})

    out_name = "summary.txt"
    out_path = os.path.join(settings.OUTPUT_DIR, out_name)
    wrote_ok = False
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(summary)
        wrote_ok = True
        logger.info(f"Summary written: path={out_path} len={len(summary)}")
    except Exception:
        logger.exception("Failed to write summary to %s", out_path)

    removed = []
    if wrote_ok:
        for it in items:
            try:
                os.remove(it["path"]) 
                removed.append(os.path.basename(it["path"]))
            except Exception:
                logger.exception("Failed to remove %s", it["path"]) 
        logger.info(f"Approved removed: count={len(removed)}")
    else:
        logger.warning("Summary not written; approved are kept")

    return JSONResponse({"ok": True, "result": "ok", "output": out_path, "removed": removed})


@app.post("/api/aggregator/publish_now")
def publish_now(limit: Optional[int] = None):
    items = _read_approved(limit or settings.BATCH_LIMIT)
    if not items:
        return JSONResponse({"ok": True, "result": "empty", "published": False})

    logger.info(f"Publish now: items={len(items)}")
    prompt = _compose_prompt(items, settings.SUMMARY_LANGUAGE)
    summary = _use_gemini(prompt)
    if not summary:
        logger.error("Gemini returned empty summary; aborting publish")
        return JSONResponse({"ok": False, "result": "gemini_failed", "published": False, "error": "empty_summary"})

    out_path = os.path.join(settings.OUTPUT_DIR, "summary.txt")
    wrote_ok = False
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(summary)
        wrote_ok = True
        logger.info(f"Summary written: path={out_path} len={len(summary)}")
    except Exception:
        logger.exception("Failed to write summary to %s", out_path)

    published = False
    if settings.BOT_TOKEN and settings.TARGET_CHANNEL_ID:
        try:
            logger.info(f"Publishing to Telegram: chat_id={settings.TARGET_CHANNEL_ID} text_len={len(summary)}")
            api_url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
            body = {
                "chat_id": settings.TARGET_CHANNEL_ID,
                "text": summary,
                "disable_web_page_preview": True,
            }
            req = urlrequest.Request(api_url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"})
            with urlrequest.urlopen(req, timeout=15) as resp:
                published = (resp.status == 200)
                if not published:
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

    removed = []
    if wrote_ok and published:
        for it in items:
            try:
                os.remove(it["path"]) 
                removed.append(os.path.basename(it["path"]))
            except Exception:
                logger.exception("Failed to remove %s", it["path"]) 
        logger.info(f"Approved removed: count={len(removed)}")
    else:
        logger.warning("Publish failed or summary not written; approved are kept")

    return JSONResponse({"ok": True, "result": "ok", "output": out_path, "removed": removed, "published": published})