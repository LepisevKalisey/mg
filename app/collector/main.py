import logging
import os
from typing import List, Optional

from fastapi import FastAPI, Body
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Load .env from project root when running locally
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_PATH = os.path.join(BASE_DIR, ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

from .config import settings
from .storage import ensure_dirs
from .telegram_client import TelegramMonitor


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
)
logger = logging.getLogger("collector.main")

app = FastAPI(title="MediaGenerator Collector", version="0.3.0")

# Single Telegram monitor instance
monitor = TelegramMonitor()


def _write_channels_file(channels: List[str]) -> None:
    os.makedirs(os.path.dirname(settings.CHANNELS_FILE), exist_ok=True)
    with open(settings.CHANNELS_FILE, "w", encoding="utf-8") as f:
        for ch in channels:
            ch = (ch or "").strip()
            if ch:
                f.write(ch + "\n")


def _state_path() -> str:
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    return os.path.join(settings.DATA_DIR, "collector_state.json")


def _load_state() -> dict:
    path = _state_path()
    if os.path.exists(path):
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            logger.warning("Failed to load state from %s", path)
    return {}


def _save_state(data: dict) -> None:
    try:
        import json
        path = _state_path()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("Failed to save state: %s", e)


@app.on_event("startup")
async def on_startup():
    # Ensure data directories exist and start monitoring (if already authorized)
    ensure_dirs(settings.DATA_DIR, settings.PENDING_DIR, settings.APPROVED_DIR, settings.SESSIONS_DIR)
    # Load persisted state (quiet flags)
    st = _load_state()
    if isinstance(st.get("quiet_mode"), bool):
        monitor.set_quiet_mode(bool(st.get("quiet_mode")))
    rng = st.get("quiet_schedule")
    if isinstance(rng, str) or rng is None:
        monitor.set_quiet_schedule(rng)
    await monitor.start()


@app.on_event("shutdown")
async def on_shutdown():
    await monitor.stop()


@app.get("/health")
async def health():
    status = "ok" if monitor.authorized else "unauthorized"
    return JSONResponse({
        "service": "collector",
        "status": status,
        "authorized": monitor.authorized,
        "channels": settings.MONITORING_CHANNELS,
        "quiet": {
            "manual": st.get("quiet_mode", False) if (st := _load_state()) else False,
            "schedule": st.get("quiet_schedule") if st else None,
            "quiet_now": monitor.is_quiet_now(),
        },
        "data_dirs": {
            "data": settings.DATA_DIR,
            "pending": settings.PENDING_DIR,
            "approved": settings.APPROVED_DIR,
            "sessions": settings.SESSIONS_DIR,
        }
    })


# Management API for bot integration
@app.get("/api/collector/channels")
async def get_channels():
    return {"ok": True, "channels": settings.MONITORING_CHANNELS}


@app.post("/api/collector/channels/add")
async def add_channel(payload: dict = Body(...)):
    channel = (payload.get("channel") or "").strip()
    if not channel:
        return JSONResponse({"ok": False, "error": "channel required"}, status_code=400)
    # Normalize leading @
    if not (channel.startswith("@") or channel.startswith("https://t.me/")):
        channel = "@" + channel
    if channel in settings.MONITORING_CHANNELS:
        return {"ok": True, "added": False, "reason": "duplicate", "channels": settings.MONITORING_CHANNELS}

    # Try to ensure subscription first; if not authorized this will be a no-op
    joined = await monitor.join_channel(channel)

    new_list = settings.MONITORING_CHANNELS + [channel]
    # Persist and apply
    _write_channels_file(new_list)
    settings.MONITORING_CHANNELS = new_list
    await monitor.set_channels(new_list)
    return {"ok": True, "added": True, "joined": joined, "channels": new_list}


@app.post("/api/collector/channels/remove")
async def remove_channel(payload: dict = Body(...)):
    channel = (payload.get("channel") or "").strip()
    if not channel:
        return JSONResponse({"ok": False, "error": "channel required"}, status_code=400)
    # Accept @name or full t.me URL; compare by string equality
    normalized = channel
    if not (normalized.startswith("@") or normalized.startswith("https://t.me/")):
        normalized = "@" + normalized
    new_list = [c for c in settings.MONITORING_CHANNELS if c != normalized]
    if len(new_list) == len(settings.MONITORING_CHANNELS):
        return {"ok": True, "removed": False, "reason": "not_found", "channels": settings.MONITORING_CHANNELS}

    # Try to leave the channel (best-effort)
    left = await monitor.leave_channel(normalized)

    _write_channels_file(new_list)
    settings.MONITORING_CHANNELS = new_list
    await monitor.set_channels(new_list)
    return {"ok": True, "removed": True, "left": left, "channels": new_list}


@app.put("/api/collector/channels")
async def replace_channels(payload: dict = Body(...)):
    channels = payload.get("channels") or []
    if not isinstance(channels, list):
        return JSONResponse({"ok": False, "error": "channels must be list"}, status_code=400)
    # normalize and deduplicate
    seen = set()
    new_list: List[str] = []
    for ch in channels:
        ch = (ch or "").strip()
        if not ch:
            continue
        if not (ch.startswith("@") or ch.startswith("https://t.me/")):
            ch = "@" + ch
        if ch not in seen:
            new_list.append(ch)
            seen.add(ch)
    _write_channels_file(new_list)
    settings.MONITORING_CHANNELS = new_list
    await monitor.set_channels(new_list)
    return {"ok": True, "channels": new_list}


@app.post("/api/collector/quiet")
async def set_quiet(payload: dict = Body(...)):
    on = bool(payload.get("on", False))
    monitor.set_quiet_mode(on)
    st = _load_state()
    st["quiet_mode"] = on
    _save_state(st)
    return {"ok": True, "quiet": monitor.is_quiet_now(), "manual": on}


@app.post("/api/collector/quiet/schedule")
async def set_quiet_schedule(payload: dict = Body(...)):
    rng: Optional[str] = payload.get("range")
    rng = (rng or "").strip() or None
    monitor.set_quiet_schedule(rng)
    st = _load_state()
    st["quiet_schedule"] = rng
    _save_state(st)
    return {"ok": True, "range": rng, "quiet_now": monitor.is_quiet_now()}