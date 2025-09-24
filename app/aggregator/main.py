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
            "1) Первая строка — короткий заголовок как жирная Markdown-ссылка на оригинальный пост: **[Заголовок](URL)**. Если URL отсутствует — просто жирный короткий заголовок без ссылки.",
            "2) Вторая строка — ровно одно релевантное эмодзи в начале строки и отсылка к источнику БЕЗ @username: используй вариативные формулировки (например: ‘📰 Как сообщает <ИмяКанала>, …’, ‘🧠 По данным <ИмяКанала>, …’, ‘📣 В канале <ИмяКанала> отмечают, …’). Не повторяй одну и ту же фразу.",
            "3) Третья строка — краткое содержание сообщения (2–4 предложения).",
            "Между материалами — одна пустая строка. Не используй списки, заголовки разделов, HTML и дополнительные пояснения. Выводи только результат в Markdown.",
        ]
    else:
        lines = [
            f"You are a digest editor. Produce a concise digest in {lang} strictly in Telegram-ready Markdown.",
            "For each item output EXACTLY three lines:",
            "1) First line — short title as a bold Markdown link to the original post: **[Title](URL)**. If URL is missing — just a bold short title without link.",
            "2) Second line — exactly one relevant emoji at the start and attribution to the source WITHOUT @username; vary the phrasing across items.",
            "3) Third line — brief summary (2–4 sentences).",
            "Separate items with a single empty line. No lists, section headers, HTML or extra explanations. Output only the Markdown result.",
        ]
    lines.append("Исходные данные по материалам (title, url, text):" if lang == "ru" else "Input items (title, url, text):")
    for it in items:
        p = it["payload"]
        # Берём заголовок сообщения, а не название канала
        title = p.get("title") or p.get("channel_title") or p.get("channel_name") or ("Канал" if lang == "ru" else "Channel")
        url = _build_message_url(p)
        text = p.get("text") or (p.get("media") or {}).get("caption") or ""
        if text and len(text) > settings.TEXT_TRUNCATE_LIMIT:
            text = text[: settings.TEXT_TRUNCATE_LIMIT] + "…"
        lines.append(f"- title: {title}")
        lines.append(f"  url: {url}")
        lines.append("  text: |")
        for ln in (text or "").splitlines():
            lines.append(f"    {ln}")
        lines.append("")
    lines.append("Выведи только итоговый дайджест в Markdown по указанным правилам." if lang == "ru" else "Output only the final Markdown digest.")
    return "\n".join(lines)


def _markdown_to_html_safe(text: str) -> str:
    """Конвертирует простые Markdown-ссылки [text](url) и жирный текст **text** в безопасный HTML.
    Поддерживаем только http/https ссылки. Сначала заменяем ссылки и жирные сегменты плейсхолдерами,
    затем экранируем текст целиком и восстанавливаем плейсхолдеры как HTML-теги.
    """
    placeholders: List[str] = []
    bold_placeholders: List[str] = []

    # 1) Ссылки -> плейсхолдеры
    def repl_link(m: Match) -> str:
        title = m.group(1)
        url = m.group(2)
        anchor = '<a href="{href}">{title}</a>'.format(href=html.escape(url, quote=True), title=html.escape(title))
        placeholders.append(anchor)
        return f"__LINK_PLACEHOLDER_{len(placeholders)-1}__"

    pattern_link = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
    tmp = pattern_link.sub(repl_link, text)

    # 2) Жирный -> плейсхолдеры
    def repl_bold(m: Match) -> str:
        inner = m.group(1)
        # Экранируем содержимое жирного сегмента, но оставляем плейсхолдеры как есть
        inner_esc = html.escape(inner)
        bold_placeholders.append(f"<b>{inner_esc}</b>")
        return f"__BOLD_PLACEHOLDER_{len(bold_placeholders)-1}__"

    pattern_bold = re.compile(r"\*\*([^*]+)\*\*")
    tmp2 = pattern_bold.sub(repl_bold, tmp)

    # 3) Экранируем оставшийся текст
    escaped = html.escape(tmp2)

    # 4) Восстанавливаем жирные сегменты
    for i, b in enumerate(bold_placeholders):
        escaped = escaped.replace(f"__BOLD_PLACEHOLDER_{i}__", b)

    # 5) Восстанавливаем якоря-ссылки
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


def _md_to_plain(text: str) -> str:
    # Преобразуем Markdown-ссылки [Текст](URL) → 'Текст - URL'
    try:
        return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 - \2", text)
    except Exception:
        return text

# -------------------- Telegram publishing --------------------

def _publish_telegram(markdown_text: str) -> bool:
    if not (settings.BOT_TOKEN and settings.TARGET_CHANNEL_ID):
        logger.warning("Telegram publishing skipped: BOT_TOKEN or TARGET_CHANNEL_ID is not set")
        return False
    try:
        api_url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
        body = {
            "chat_id": settings.TARGET_CHANNEL_ID,
            "text": markdown_text,
            "disable_web_page_preview": settings.TELEGRAM_DISABLE_WEB_PREVIEW,
        }
        # parse_mode добавляем только если он задан
        if settings.TELEGRAM_PARSE_MODE:
            body["parse_mode"] = settings.TELEGRAM_PARSE_MODE
        logger.info(
            f"Publishing to Telegram: chat_id={settings.TARGET_CHANNEL_ID} text_len={len(markdown_text)} parse_mode={settings.TELEGRAM_PARSE_MODE}"
        )
        req = urlrequest.Request(
            api_url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urlrequest.urlopen(req, timeout=settings.TELEGRAM_TIMEOUT_SEC) as resp:
            status = resp.status
            raw = ""
            try:
                raw = resp.read().decode("utf-8", errors="ignore")
            except Exception:
                raw = ""
            if status != 200:
                logger.warning(f"Bot API non-200 response: {status} body={raw[:200]}")
                return False
            # Парсим JSON и проверяем поле ok
            try:
                j = json.loads(raw)
            except Exception:
                j = None
            if isinstance(j, dict):
                if not j.get("ok", False):
                    desc = j.get("description", "") or ""
                    logger.error(f"Bot API returned ok=false: {desc}")
                    # Фолбэк при ошибке парсинга сущностей
                    if "can't parse entities" in desc.lower():
                        try:
                            plain = _md_to_plain(markdown_text)
                            body2 = {
                                "chat_id": settings.TARGET_CHANNEL_ID,
                                "text": plain,
                                "disable_web_page_preview": settings.TELEGRAM_DISABLE_WEB_PREVIEW,
                            }
                            req2 = urlrequest.Request(
                                api_url,
                                data=json.dumps(body2, ensure_ascii=False).encode("utf-8"),
                                headers={"Content-Type": "application/json"},
                            )
                            with urlrequest.urlopen(req2, timeout=settings.TELEGRAM_TIMEOUT_SEC) as resp2:
                                raw2 = ""
                                try:
                                    raw2 = resp2.read().decode("utf-8", errors="ignore")
                                except Exception:
                                    raw2 = ""
                                try:
                                    j2 = json.loads(raw2)
                                except Exception:
                                    j2 = None
                                ok2 = bool(j2 and j2.get("ok", False))
                                if not ok2:
                                    logger.warning(f"Retry Bot API ok=false: {raw2[:200]}")
                                return ok2
                        except Exception as e2:
                            logger.exception(f"Retry without parse_mode failed: {e2}")
                    return False
            else:
                # Если не JSON — считаем это ошибкой
                logger.warning(f"Bot API returned non-JSON body: {raw[:200]}")
                return False
            # Успех
            return True
    except HTTPError as he:
        # Пробуем прочитать тело ошибки
        try:
            err_body = he.read().decode("utf-8")
        except Exception:
            err_body = str(he)
        logger.error(f"Bot API HTTPError: {he.code} {err_body}")
        # Если это ошибка парсинга сущностей — пробуем отправить без parse_mode и с plain-текстом
        if he.code == 400 and "can't parse entities" in err_body.lower():
            try:
                plain = _md_to_plain(markdown_text)
                body2 = {
                    "chat_id": settings.TARGET_CHANNEL_ID,
                    "text": plain,
                    "disable_web_page_preview": settings.TELEGRAM_DISABLE_WEB_PREVIEW,
                }
                req2 = urlrequest.Request(
                    api_url,
                    data=json.dumps(body2, ensure_ascii=False).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with urlrequest.urlopen(req2, timeout=settings.TELEGRAM_TIMEOUT_SEC) as resp2:
                    raw2 = resp2.read().decode("utf-8", errors="ignore")
                    try:
                        j2 = json.loads(raw2)
                    except Exception:
                        j2 = None
                    ok2 = bool(j2 and j2.get("ok", False))
                    if not ok2:
                        logger.warning(f"Retry Bot API ok=false: {raw2[:200]}")
                    return ok2
            except Exception as e2:
                logger.exception(f"Retry without parse_mode failed: {e2}")
        # Иначе — обычный фолбэк
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

    # Пост-обработка формата
    summary = _postprocess_summary(summary)

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

    # Пост-обработка формата
    summary = _postprocess_summary(summary)

    out_path = os.path.join(settings.OUTPUT_DIR, settings.OUTPUT_SUMMARY_FILENAME)
    wrote_ok = _write_summary_file(out_path, summary, encoding=settings.SUMMARY_FILE_ENCODING_PUBLISH)

    # Публикация в Telegram
    text_to_send = summary
    if settings.TELEGRAM_PARSE_MODE and settings.TELEGRAM_PARSE_MODE.upper() == "HTML":
        text_to_send = _markdown_to_html_safe(summary)
    published = _publish_telegram(text_to_send)

    removed: List[str] = []
    if published:
        removed = _remove_approved(items)

    return JSONResponse({"ok": True, "result": "ok", "published": published, "output": out_path, "removed": removed})


def _build_message_url(payload: Dict[str, Any]) -> str:
    username = payload.get("channel_username")
    msg_id = payload.get("message_id")
    chan_id = payload.get("channel_id")
    try:
        if username and msg_id:
            return f"https://t.me/{username}/{msg_id}"
        if chan_id and msg_id:
            # Для приватных групп/каналов используем t.me/c/<short_id>/<msg_id>
            cid = int(chan_id)
            if cid < 0:
                cid = -cid
            # short id без префикса 100...
            short_id = cid - 1000000000000 if str(cid).startswith("100") else cid
            return f"https://t.me/c/{short_id}/{msg_id}"
    except Exception:
        pass
    return ""

_emoji_re = re.compile(r"^([\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u27FF])(?:\s*[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u27FF]+)*\s*(.*)$")
_username_paren_re = re.compile(r"\s*\(@[A-Za-z0-9_]+\)")

def _postprocess_summary(text: str) -> str:
    lines = text.splitlines()
    out: List[str] = []
    first_in_block = True
    for ln in lines:
        if not ln.strip():
            out.append(ln)
            first_in_block = True
            continue
        cur = ln
        if first_in_block:
            # Заголовок — если это ссылка или просто текст, обернём в ** ** если не обёрнут
            if cur.startswith("**") and cur.endswith("**"):
                pass
            else:
                cur = f"**{cur}**"
            first_in_block = False
        else:
            # Вторая строка: один эмодзи в начале
            m = _emoji_re.match(cur)
            if m:
                cur = f"{m.group(1)} {m.group(2)}".strip()
            # Убрать (@username) в скобках
            cur = _username_paren_re.sub("", cur)
        out.append(cur)
    return "\n".join(out)

    removed: List[str] = []
    if wrote_ok:
        removed = _remove_approved(items)
    else:
        logger.warning("Summary not written; approved are kept")

    return JSONResponse({"ok": True, "result": "ok", "output": out_path, "removed": removed})