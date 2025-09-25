import logging
import time
from typing import Dict, Any, Optional, List
from threading import Timer, Lock

from fastapi import FastAPI, Body
from fastapi.responses import JSONResponse

from .config import settings
import os
import glob
import json

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("scheduler.main")

app = FastAPI(title="MediaGenerator Scheduler", version="0.1.0")

# In-memory queues keyed by channel_id
_queues: Dict[str, List[Dict[str, Any]]] = {}
# Debounce timers per channel
_timers: Dict[str, Timer] = {}
_due_at: Dict[str, Optional[float]] = {}
_lock = Lock()


def _rest_call(method: str, url: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Optional[Dict[str, Any]]:
    import json
    from urllib import request as urlrequest
    try:
        if method.upper() == "GET":
            with urlrequest.urlopen(url, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                return json.loads(raw)
        else:
            data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
            req = urlrequest.Request(url, data=data, headers={"Content-Type": "application/json"}, method=method.upper())
            with urlrequest.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                return json.loads(raw)
    except Exception:
        logger.exception("REST call failed: %s %s", method, url)
        return None


def _read_approved(limit: int) -> list:
    pattern = os.path.join(settings.APPROVED_DIR, "*.json")
    files = sorted(glob.glob(pattern))
    logger.info("Approved scan: dir=%s pattern=%s matched=%d", settings.APPROVED_DIR, pattern, len(files))
    if limit and limit > 0:
        files = files[:limit]
    items = []
    for p in files:
        try:
            with open(p, "r", encoding="utf-8") as f:
                payload = json.load(f)
            items.append({"path": p, "payload": payload})
        except Exception:
            logger.exception("Failed to read %s", p)
    return items

# Build Telegram message URL similar to aggregator
def _build_message_url(payload: Dict[str, Any]) -> str:
    username = payload.get("channel_username")
    msg_id = payload.get("message_id")
    chan_id = payload.get("channel_id")
    try:
        if username and msg_id:
            return f"https://t.me/{username}/{msg_id}"
        if chan_id and msg_id:
            cid = int(chan_id)
            if cid < 0:
                cid = -cid
            short_id = cid - 1000000000000 if str(cid).startswith("100") else cid
            return f"https://t.me/c/{short_id}/{msg_id}"
    except Exception:
        pass
    return ""


def _flush_channel(channel_id: str) -> None:
    # Read approved items from storage (Stage 3 pipeline)
    approved = _read_approved(settings.BATCH_LIMIT)
    if not approved:
        logger.info("Flush: channel=%s no approved items", channel_id)
        return
    logger.info("Flush: channel=%s approved_items=%d", channel_id, len(approved))

    # Prepare items for summarizer
    summ_items: List[Dict[str, Any]] = []
    for it in approved:
        p = it.get("payload", {})
        title = p.get("title") or p.get("channel_title") or p.get("channel_name") or ""
        url = _build_message_url(p)
        text = p.get("text") or (p.get("media") or {}).get("caption") or ""
        source = p.get("channel_title") or p.get("channel_name") or ""
        summ_items.append({
            "title": title,
            "url": url,
            "text": text,
            "source": source,
        })

    # Call Summarizer
    summary_text: Optional[str] = None
    try:
        if not settings.SUMMARIZER_URL:
            logger.warning("Summarizer URL not configured; skipping summarization")
        else:
            s_url = settings.SUMMARIZER_URL.rstrip("/") + "/api/summarizer/summarize"
            payload = {
                "items": summ_items,
                "lang": settings.SUMMARY_LANGUAGE,
                "truncate_limit": settings.TEXT_TRUNCATE_LIMIT,
                # parse_mode left default; Publisher controls formatting
            }
            resp = _rest_call("POST", s_url, payload) or {}
            if resp.get("ok"):
                summary_text = (resp.get("summary") or "").strip()
                logger.info("Summarizer ok: text_len=%d", len(summary_text or ""))
            else:
                logger.warning("Summarizer returned not ok: %s", resp)
    except Exception:
        logger.exception("Summarizer call failed")

    if not summary_text:
        logger.info("No summary text; aborting publish for channel=%s", channel_id)
        return

    # Call Publisher
    published_ok = False
    try:
        if not settings.PUBLISHER_URL:
            logger.warning("Publisher URL not configured; skipping publish")
        else:
            p_url = settings.PUBLISHER_URL.rstrip("/") + "/api/publisher/publish"
            resp2 = _rest_call("POST", p_url, {"text": summary_text}) or {}
            published_ok = bool(resp2.get("ok"))
            logger.info("Publisher result ok=%s", published_ok)
    except Exception:
        logger.exception("Publisher call failed")

    # Remove approved items if published
    if published_ok:
        removed = []
        for it in approved:
            path = it.get("path")
            try:
                if path:
                    os.remove(path)
                    removed.append(os.path.basename(path))
            except Exception:
                logger.exception("Failed to remove %s", path)
        logger.info("Approved removed: count=%d", len(removed))

    # finally clear in-memory queue for the channel
    _queues[channel_id] = []


def _schedule(channel_id: str, wait_sec: Optional[int]) -> bool:
    delay = wait_sec if (isinstance(wait_sec, int) and wait_sec > 0) else settings.DEBOUNCE_SECONDS
    if delay <= 0:
        return False
    def fire():
        with _lock:
            _timers.pop(channel_id, None)
            _due_at[channel_id] = None
        _flush_channel(channel_id)
    with _lock:
        t = _timers.get(channel_id)
        if t:
            try:
                t.cancel()
            except Exception:
                pass
        _due_at[channel_id] = time.time() + delay
        timer = Timer(delay, fire)
        timer.daemon = True
        timer.start()
        _timers[channel_id] = timer
        logger.info("Scheduled channel=%s in %ds due_at=%s", channel_id, delay, _due_at[channel_id])
    return True


@app.get("/health")
async def health():
    return JSONResponse({
        "ok": True,
        "status": "ok",
        "service": "scheduler",
        "next_fire_time": _due_at,
    })


@app.get("/ready")
async def ready():
    return JSONResponse({
        "ok": True,
        "ready": True,
        "service": "scheduler",
    })


@app.post("/api/scheduler/publish_soon")
async def publish_soon(payload: Dict[str, Any] = Body(...)):
    channel_id = str(payload.get("channel_id") or "default")
    items = payload.get("items") or []
    wait_sec = payload.get("wait_sec")
    # Append items to in-memory queue
    try:
        with _lock:
            q = _queues.get(channel_id) or []
            # Normalize items to dicts with id and optional fields
            for it in items:
                if isinstance(it, dict) and it.get("id"):
                    q.append(it)
            _queues[channel_id] = q
    except Exception:
        logger.exception("Queue append failed for channel=%s", channel_id)
    scheduled = _schedule(channel_id, wait_sec if isinstance(wait_sec, int) else None)
    due_at = None
    with _lock:
        due_at = _due_at.get(channel_id)
    return JSONResponse({
        "ok": True,
        "scheduled_for": (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(due_at)) if due_at else None),
        "batch_key": channel_id,
    })


@app.post("/api/scheduler/flush")
async def flush(payload: Dict[str, Any] = Body(...)):
    channel_id = str(payload.get("channel_id") or "default")
    _flush_channel(channel_id)
    return JSONResponse({"ok": True, "flushed": True})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)