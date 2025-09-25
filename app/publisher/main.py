import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import FastAPI, Body
from fastapi.responses import JSONResponse

from .config import settings
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("publisher.main")

app = FastAPI(title="MediaGenerator Publisher", version="0.1.0")


def _md_to_plain(text: str) -> str:
    import re
    try:
        return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 - \2", text)
    except Exception:
        return text


def _publish_telegram(markdown_text: str, parse_mode: Optional[str]) -> bool:
    if not (settings.BOT_TOKEN and settings.TARGET_CHANNEL_ID):
        try:
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
            fname = f"dry_{ts}.md"
            fpath = os.path.join(settings.OUTPUT_DIR, fname)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(markdown_text)
            logger.warning(
                f"Telegram publishing skipped (no BOT_TOKEN/TARGET_CHANNEL_ID). Dry-run saved: {fpath} (len={len(markdown_text)})"
            )
            return True
        except Exception as e:
            logger.exception(f"Dry-run write failed: {e}")
            return False
    try:
        api_url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
        body = {
            "chat_id": settings.TARGET_CHANNEL_ID,
            "text": markdown_text,
            "disable_web_page_preview": settings.TELEGRAM_DISABLE_WEB_PREVIEW,
        }
        if parse_mode:
            body["parse_mode"] = parse_mode
        logger.info(
            f"Publishing to Telegram: chat_id={settings.TARGET_CHANNEL_ID} text_len={len(markdown_text)} parse_mode={parse_mode}"
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
            try:
                j = json.loads(raw)
            except Exception:
                j = None
            if isinstance(j, dict) and not j.get("ok", False):
                desc = j.get("description", "") or ""
                logger.error(f"Bot API returned ok=false: {desc}")
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
            elif not isinstance(j, dict):
                logger.warning(f"Bot API returned non-JSON body: {raw[:200]}")
                return False
            return True
    except HTTPError as he:
        try:
            err_body = he.read().decode("utf-8")
        except Exception:
            err_body = str(he)
        logger.error(f"Bot API HTTPError: {he.code} {err_body}")
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
    except URLError as ue:
        logger.error(f"Bot API URLError: {ue}")
    except Exception as e:
        logger.exception(f"Bot API request failed: {e}")
    return False


@app.get("/health")
async def health():
    return JSONResponse({"ok": True, "status": "ok", "service": "publisher"})


@app.post("/api/publisher/publish")
async def publish(payload: Dict[str, Any] = Body(...)):
    text = payload.get("text") or ""
    parse_mode = payload.get("parse_mode") or settings.TELEGRAM_PARSE_MODE
    if not text:
        return JSONResponse({"ok": False, "result": "empty_text"})
    ok = _publish_telegram(text, parse_mode)
    return JSONResponse({"ok": ok, "result": "ok" if ok else "failed"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)