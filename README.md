# MG Digest Bot

This repository hosts the development of a Telegram-based digest system. The project aims to collect posts from selected channels, summarize them, and publish curated digests.

For a detailed technical specification, see [docs/TECH_SPEC.md](docs/TECH_SPEC.md).

## Monitoring

Logging is provided via **structlog** in JSON format. Prometheus metrics such as `ingest_posts_total` and `summary_latency_seconds` are exposed together with a `/health` endpoint by `app.common.metrics.start_metrics_server`.

Alerting helpers in `app.common.alerts` emit structured log events for situations like master session invalidation, LLM circuit breaker activation, digest publication failures, and empty digest releases.
