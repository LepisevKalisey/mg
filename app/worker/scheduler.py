"""Cron-based scheduler for digest assembly.

This module avoids external dependencies to keep the project lightweight.
It implements a very small subset of cron syntax and exposes simple
``/health`` and ``/metrics`` HTTP endpoints using the standard library.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Set, Tuple
from zoneinfo import ZoneInfo
import threading

from app.common.config import load_config
from app.common.logging import setup_logging

logger = setup_logging()

# In-memory metric for how many times a digest was triggered.
DIGEST_TRIGGERED_TOTAL = 0


# ---------------------------------------------------------------------------
# Cron parsing helpers
# ---------------------------------------------------------------------------

def _parse_cron_part(part: str, minimum: int, maximum: int) -> Set[int]:
    """Parse a single cron field into a set of allowed integers."""
    values: Set[int] = set()
    for token in part.split(","):
        token = token.strip()
        if token == "*":
            values.update(range(minimum, maximum + 1))
        elif token.startswith("*/"):
            step = int(token[2:])
            values.update(range(minimum, maximum + 1, step))
        elif "-" in token:
            start_s, end_s = token.split("-", 1)
            start, end = int(start_s), int(end_s)
            values.update(range(start, end + 1))
        else:
            values.add(int(token))
    return values


def parse_cron(expr: str) -> Tuple[Set[int], Set[int], Set[int], Set[int], Set[int]]:
    """Parse ``expr`` (five-field cron) into sets of allowed values."""
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError("cron expression must have 5 fields")
    minute = _parse_cron_part(parts[0], 0, 59)
    hour = _parse_cron_part(parts[1], 0, 23)
    day = _parse_cron_part(parts[2], 1, 31)
    month = _parse_cron_part(parts[3], 1, 12)
    weekday = _parse_cron_part(parts[4], 0, 6)
    return minute, hour, day, month, weekday


def _cron_match(dt: datetime, fields: Tuple[Set[int], Set[int], Set[int], Set[int], Set[int]]) -> bool:
    minute, hour, day, month, weekday = fields
    return (
        dt.minute in minute
        and dt.hour in hour
        and dt.day in day
        and dt.month in month
        and dt.weekday() in weekday
    )


# ---------------------------------------------------------------------------
# Digest trigger and scheduler loop
# ---------------------------------------------------------------------------
async def trigger_digest() -> None:
    """Trigger digest assembly."""
    global DIGEST_TRIGGERED_TOTAL
    DIGEST_TRIGGERED_TOTAL += 1
    logger.info("Triggering digest generation")
    
    try:
        from app.worker.digest import generate_digest
        result = await generate_digest()
        logger.info(f"Digest generated successfully: {result['id']}")
    except Exception as e:
        logger.error(f"Error generating digest: {e}")
        raise


async def scheduler_loop(fields, tz: ZoneInfo) -> None:
    """Run forever and invoke :func:`trigger_digest` on schedule."""
    while True:
        now = datetime.now(tz)
        if _cron_match(now, fields):
            await trigger_digest()
        # sleep until next minute boundary
        next_minute = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
        sleep_for = (next_minute - datetime.now(tz)).total_seconds()
        await asyncio.sleep(max(sleep_for, 0))


# ---------------------------------------------------------------------------
# Simple HTTP endpoints
# ---------------------------------------------------------------------------
class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # pragma: no cover - thin wrapper
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        elif self.path == "/metrics":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.end_headers()
            body = f"digest_triggered_total {DIGEST_TRIGGERED_TOTAL}\n".encode()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


def start_http_server(port: int) -> HTTPServer:
    """Start a background HTTP server for health and metrics."""
    server = HTTPServer(("0.0.0.0", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
async def main() -> None:
    config = load_config()
    digest_cfg = config.get("digest", {})
    cron_expr = digest_cfg.get("cron", "0 9 * * *")
    tz_name = digest_cfg.get("tz", "UTC")
    tz = ZoneInfo(tz_name)
    fields = parse_cron(cron_expr)

    port = int(config.get("PORT", 8000))
    start_http_server(port)
    logger.info("scheduler started", cron=cron_expr, tz=tz_name, port=port)
    await scheduler_loop(fields, tz)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
