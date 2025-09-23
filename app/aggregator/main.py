import os
import json
import glob
import logging
import re
import html
from typing import List, Dict, Any, Optional, Match

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


# -------------------- IO helpers --------------------

def _write_summary_file(path: str, content: str, *, encoding: str) -> bool:
    try:
        with open(path, "w", encoding=encoding) as f:
            f.write(content)
        logger.info(f"Summary written: path={path} len={len(content)} encoding={encoding}")
        return True
    except Exception:
        logger.exception("Failed to write summary to %s", path)
        return False


def _remove_approved(items: List[Dict[str, Any]]) -> List[str]:
    removed: List[str] = []
    for it in items:
        try:
            os.remove(it["path"])  # type: ignore[arg-type]
            removed.append(os.path.basename(it["path"]))
        except Exception:
            logger.exception("Failed to remove %s", it["path"])  # type: ignore[index]
    logger.info(f"Approved removed: count={len(removed)}")
    return removed


# -------------------- Data loading --------------------

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


# -------------------- Prompt & LLM --------------------

def _compose_prompt(items: List[Dict[str, Any]], lang: str) -> str:
    # Инструкция модели: строгий Markdown-формат для Telegram
    if lang == "ru":
        lines: List[str] = [
            "Ты — редактор дайджестов. Сформируй краткий дайджест на русском языке строго в формате Markdown для публикации в Telegram.",
            "Для каждого материала выведи РОВНО три строки:",
            "1) Первая строка — короткий заголовок как Markdown-ссылка на оригинальный пост: [Заголовок](URL). Если URL отсутствует — просто короткий заголовок без ссылки.",
            "2) Вторая строка — ровно одно релевантное эмодзи в начале строки и отсылка к источнику: например ‘📰 Канал <ИмяКанала> (@username) сообщает, что …’ или ‘🧠 Как написали в ForbesRussia, …’.",
            "3) Третья строка — краткое содержание сообщения (1–2 предложения).",
            "Между материалами — одна пустая строка. Не используй списки, заголовки разделов, HTML и дополнительные пояснения. Выводи только результат в Markdown.",
        ]
    else:
        lines = [
            f"You are a digest editor. Produce a concise digest in {lang} strictly in Telegram-ready Markdown.",
            "For each item output EXACTLY three lines:",
            "1) First line — short title as a Markdown link to the original post: [Title](URL). If URL is missing — just a short title without link.",
            "2) Second line — exactly one relevant emoji at the start and attribution to the source.",
            "3) Third line — brief summary (1–2 sentences).",
            "Separate items with a single empty line. No lists, section headers, HTML or extra explanations. Output only the Markdown result.",
        ]
    lines.append("Исходные данные по материалам (title, url, text):" if lang == "ru" else "Input items (title, url, text):")
    for it in items:
        p = it["payload"]
        title = p.get("channel_title") or p.get("channel_name") or ("Канал" if lang == "ru" else "Channel")
        username = p.get("channel_username")
        msg_id = p.get("message_id")
        url = f"https://t.me/{username}/{msg_id}" if username and msg_id else ""
        text = p.get("text") or (p.get("media") or {}).get("caption") or ""
        if text and len(text) > settings.TEXT_TRUNCATE_LIMIT:
            text = text[: settings.TEXT_TRUNCATE_LIMIT] + "…"
        # Структурируем, чтобы модели было проще
        lines.append(f"- title: {title}")
        lines.append(f"  url: {url}")
        lines.append("  text: |")
        for ln in (text or "").splitlines():
            lines.append(f"    {ln}")
        lines.append("")
    lines.append("Выведи только итоговый дайджест в Markdown по указанным правилам." if lang == "ru" else "Output only the final Markdown digest.")
    return "\n".join(lines)


def _markdown_to_html_safe(text: str) -> str:
    """Конвертирует простые Markdown-ссылки [text](url) в <a href="url">text</a>
    и экранирует остальной текст для безопасной отправки как HTML в Bot API.
    Поддерживаем только http/https ссылки. Эмодзи и кириллица сохраняются.
    """
    # 1) Заменим Markdown-ссылки на плейсхолдеры
    placeholders: List[str] = []
    def repl(m: Match) -> str:
        title = m.group(1)
        url = m.group(2)
        anchor = f'<a href="{html.escape(url, quote=True)}">{html.escape(title)}</a>'
        placeholders.append(anchor)
        return f"__LINK_PLACEHOLDER_{len(placeholders)-1}__"

    pattern = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
    tmp = pattern.sub(repl, text)

    # 2) Экранируем весь текст как HTML
    escaped = html.escape(tmp)

    # 3) Возвращаем плейсхолдеры якорями
    for i, a in enumerate(placeholders):
        escaped = escaped.replace(f"__LINK_PLACEHOLDER_{i}__", a)

    return escaped


# -------------------- LLM call --------------------

def _use_gemini(prompt: str) -> str:
    try:
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model_name = settings.GEMINI_MODEL_NAME
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


# -------------------- Telegram publishing --------------------

def _publish_telegram(markdown_text: str) -> bool:
    if not (settings.BOT_TOKEN and settings.TARGET_CHANNEL_ID):
        logger.warning("Telegram publishing skipped: BOT_TOKEN or TARGET_CHANNEL_ID is not set")
        return False
    try:
        html_text = _markdown_to_html_safe(markdown_text)
        api_url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
        body = {
            "chat_id": settings.TARGET_CHANNEL_ID,
            "text": html_text,
            "disable_web_page_preview": settings.TELEGRAM_DISABLE_WEB_PREVIEW,
            "parse_mode": settings.TELEGRAM_PARSE_MODE,
        }
        logger.info(
            f"Publishing to Telegram: chat_id={settings.TARGET_CHANNEL_ID} text_len={len(markdown_text)} parse_mode={settings.TELEGRAM_PARSE_MODE}"
        )
        req = urlrequest.Request(
            api_url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urlrequest.urlopen(req, timeout=settings.TELEGRAM_TIMEOUT_SEC) as resp:
            ok = (resp.status == 200)
            if not ok:
                logger.warning(f"Bot API non-200 response: {resp.status}")
            return ok
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
    return False


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

    out_name = settings.OUTPUT_SUMMARY_FILENAME
    out_path = os.path.join(settings.OUTPUT_DIR, out_name)
    wrote_ok = _write_summary_file(out_path, summary, encoding=settings.SUMMARY_FILE_ENCODING_RUN)

    removed: List[str] = []
    if wrote_ok:
        removed = _remove_approved(items)
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

    out_path = os.path.join(settings.OUTPUT_DIR, settings.OUTPUT_SUMMARY_FILENAME)
    wrote_ok = _write_summary_file(out_path, summary, encoding=settings.SUMMARY_FILE_ENCODING_PUBLISH)

    published = _publish_telegram(summary)

    removed: List[str] = []
    if wrote_ok and published:
        removed = _remove_approved(items)
    else:
        logger.warning("Publish failed or summary not written; approved are kept")

    return JSONResponse({"ok": True, "result": "ok", "output": out_path, "removed": removed, "published": published})