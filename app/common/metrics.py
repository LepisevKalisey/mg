"""Prometheus metrics definitions and helpers."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:  # pragma: no cover - dependency might be missing at runtime
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Histogram,
        generate_latest,
    )
except Exception:  # pragma: no cover
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"  # type: ignore
    Counter = Histogram = None  # type: ignore

    def generate_latest(*args, **kwargs):  # type: ignore
        return b""


import structlog

logger = structlog.get_logger()

# Metric definitions
INGEST_POSTS_TOTAL = Counter("ingest_posts_total", "Total number of posts ingested")
SUMMARY_LATENCY_SECONDS = Histogram(
    "summary_latency_seconds", "Latency of summary generation in seconds"
)
LLM_ERRORS_TOTAL = Counter("llm_errors_total", "Total number of LLM provider errors")
PUBLISH_FAILURES_TOTAL = Counter(
    "publish_failures_total", "Total number of digest publication failures"
)


class _MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler exposing /metrics and /health endpoints."""

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if self.path == "/metrics":
            data = generate_latest()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()


def start_metrics_server(port: int = 8000) -> ThreadingHTTPServer:
    """Start a background HTTP server exposing metrics and health endpoints."""
    server = ThreadingHTTPServer(("", port), _MetricsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("metrics_server_started", port=port)
    return server


__all__ = [
    "INGEST_POSTS_TOTAL",
    "SUMMARY_LATENCY_SECONDS",
    "LLM_ERRORS_TOTAL",
    "PUBLISH_FAILURES_TOTAL",
    "start_metrics_server",
]
