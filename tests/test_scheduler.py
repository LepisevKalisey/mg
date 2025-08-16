import asyncio
import http.client
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Ensure project root on sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.worker import scheduler


def test_parse_cron_and_match():
    fields = scheduler.parse_cron("0 9 * * *")
    dt_ok = datetime(2024, 1, 1, 9, 0, tzinfo=ZoneInfo("UTC"))
    assert scheduler._cron_match(dt_ok, fields)  # type: ignore[attr-defined]
    dt_bad = datetime(2024, 1, 1, 10, 0, tzinfo=ZoneInfo("UTC"))
    assert not scheduler._cron_match(dt_bad, fields)  # type: ignore[attr-defined]


def test_health_and_metrics_endpoints():
    server = scheduler.start_http_server(0)
    port = server.server_port

    # Health
    conn = http.client.HTTPConnection("127.0.0.1", port)
    conn.request("GET", "/health")
    resp = conn.getresponse()
    assert resp.status == 200
    assert resp.read() == b"ok"

    # Metrics
    asyncio.run(scheduler.trigger_digest())
    conn.request("GET", "/metrics")
    resp = conn.getresponse()
    body = resp.read().decode()
    assert "digest_triggered_total 1" in body

    server.shutdown()
