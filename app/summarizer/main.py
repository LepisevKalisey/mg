import os
import json
import logging
import html
import re
from typing import List, Dict, Any, Optional, Match

from fastapi import FastAPI, Body
from fastapi.responses import JSONResponse

from .config import settings
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("summarizer.main")

app = FastAPI(title="MediaGenerator Summarizer", version="0.1.0")


def _write_summary_file(path: str, content: str, *, encoding: str) -> bool:
    try:
        with open(path, "w", encoding=encoding) as f:
            f.write(content)
        logger.info(f"Summary written: path={path} len={len(content)} encoding={encoding}")
        return True
    except Exception:
        logger.exception("Failed to write summary to %s", path)
        return False


def _compose_prompt(items: List[Dict[str, Any]], lang: str, truncate_limit: int) -> str:
    if lang == "ru":
        lines: List[str] = [
            "Ты — редактор дайджестов. Сформируй один общий пост на русском языке строго в формате Markdown для публикации в Telegram.",
            "Сгруппируй материалы по смысловым темам: если несколько материалов об одном и том же, объедини их в один блок.",
            "Для КАЖДОГО смыслового блока выведи РОВНО три строки:",
            "1) Первая строка — короткий заголовок как жирная Markdown-ссылка на основной первоисточник: **[Заголовок](URL)**. Если URL отсутствует — просто жирный короткий заголовок без ссылки.",
            "2) Вторая строка — ровно одно релевантное эмодзи в начале строки и отсылки ко ВСЕМ первоисточникам (в виде Markdown-ссылок [Имя](URL) или упоминаний по названию канала без @username). Не повторяй одну и ту же фразу.",
            "3) Третья строка — краткое интегрированное содержание (2–4 предложения) по теме блока.",
            "Между блоками — одна пустая строка. Не используй списки, заголовки разделов, HTML и дополнительные пояснения. Выводи только результат в Markdown.",
        ]
    else:
        lines = [
            f"You are a digest editor. Produce a single combined post in {lang} strictly in Telegram-ready Markdown.",
            "Cluster items by topic: if several items are about the same thing, merge them into one block.",
            "For EACH topical block output EXACTLY three lines:",
            "1) First line — short title as a bold Markdown link to the primary source: **[Title](URL)**. If URL is missing — just a bold short title without link.",
            "2) Second line — exactly one relevant emoji at the start and references to ALL sources (as Markdown links [Name](URL) or source names without @username). Vary the phrasing.",
            "3) Third line — brief integrated summary (2–4 sentences) for that topic.",
            "Separate blocks with a single empty line. No lists, section headers, HTML or extra explanations. Output only the Markdown result.",
        ]
    lines.append("Исходные данные по материалам (title, url, source, text):" if lang == "ru" else "Input items (title, url, source, text):")
    for it in items:
        p = it
        title = p.get("title") or p.get("channel_title") or p.get("channel_name") or ("Канал" if lang == "ru" else "Channel")
        url = p.get("url") or ""
        text = p.get("text") or ""
        source_name = p.get("source") or p.get("channel_title") or p.get("channel_name") or ""
        if text and len(text) > truncate_limit:
            text = text[: truncate_limit] + "…"
        lines.append(f"- title: {title}")
        lines.append(f"  url: {url}")
        lines.append(f"  source: {source_name}")
        lines.append("  text: |")
        for ln in (text or "").splitlines():
            lines.append(f"    {ln}")
        lines.append("")
    lines.append("Выведи только итоговый пост, сгруппированный по смысловым блокам, в Markdown по указанным правилам." if lang == "ru" else "Output only the final Markdown post grouped by topical blocks.")
    return "\n".join(lines)


# Markdown->HTML safe, reuse aggregator logic
_bold_re = re.compile(r"\*\*([^*]+)\*\*")
_link_re = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")

def _markdown_to_html_safe(text: str) -> str:
    placeholders: List[str] = []
    bold_placeholders: List[str] = []

    def repl_link(m: Match) -> str:
        title = m.group(1)
        url = m.group(2)
        anchor = '<a href="{href}">{title}</a>'.format(href=html.escape(url, quote=True), title=html.escape(title))
        placeholders.append(anchor)
        return f"__LINK_PLACEHOLDER_{len(placeholders)-1}__"

    tmp = _link_re.sub(repl_link, text)

    def repl_bold(m: Match) -> str:
        inner = m.group(1)
        inner_esc = html.escape(inner)
        bold_placeholders.append(f"<b>{inner_esc}</b>")
        return f"__BOLD_PLACEHOLDER_{len(bold_placeholders)-1}__"

    tmp2 = _bold_re.sub(repl_bold, tmp)

    escaped = html.escape(tmp2)

    for i, b in enumerate(bold_placeholders):
        escaped = escaped.replace(f"__BOLD_PLACEHOLDER_{i}__", b)

    for i, a in enumerate(placeholders):
        escaped = escaped.replace(f"__LINK_PLACEHOLDER_{i}__", a)

    return escaped


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


@app.get("/health")
async def health():
    return JSONResponse({"ok": True, "status": "ok", "service": "summarizer"})


@app.post("/api/summarizer/summarize")
async def summarize(payload: Dict[str, Any] = Body(...)):
    items = payload.get("items") or []
    lang = payload.get("lang") or settings.SUMMARY_LANGUAGE
    truncate_limit = int(payload.get("truncate_limit") or settings.TEXT_TRUNCATE_LIMIT)
    parse_mode = (payload.get("parse_mode") or "Markdown").upper()

    if not items:
        return JSONResponse({"ok": True, "result": "empty", "summary": ""})

    prompt = _compose_prompt(items, lang, truncate_limit)
    summary = _use_gemini(prompt)
    # Fallback summary when LLM fails
    if not summary:
        try:
            fb_lines: List[str] = []
            for it in items:
                title = it.get("title") or ("Канал" if lang == "ru" else "Channel")
                url = it.get("url") or ""
                source = it.get("source") or ""
                text = it.get("text") or ""
                if text and len(text) > truncate_limit:
                    text = text[:truncate_limit] + "…"
                first = f"**[{title}]({url})**" if url else f"**{title}**"
                second = ("📰 " + source).strip()
                third = text if text else ("Краткое содержание недоступно." if lang == "ru" else "Summary unavailable.")
                fb_lines.extend([first, second, third, ""])
            summary = "\n".join(fb_lines).strip()
            logger.info(f"Fallback summary generated: len={len(summary)}")
        except Exception:
            logger.exception("Fallback summary generation failed")
            return JSONResponse({"ok": False, "result": "gemini_failed", "error": "empty_summary"})

    # Postprocess
    summary_md = summary
    summary_html = _markdown_to_html_safe(summary) if parse_mode == "HTML" else None

    # Optionally write output for compatibility
    out_path = os.path.join(settings.OUTPUT_DIR, settings.OUTPUT_SUMMARY_FILENAME)
    wrote_ok = _write_summary_file(out_path, summary_md, encoding=settings.SUMMARY_FILE_ENCODING)

    return JSONResponse({
        "ok": True,
        "result": "ok",
        "summary": summary_md,
        "summary_html": summary_html,
        "output": out_path,
        "wrote_ok": wrote_ok,
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)