# MG Digest Bot

This repository hosts the development of a Telegram-based digest system. The project aims to collect posts from selected channels, summarize them, and publish curated digests.

For a detailed technical specification, see [docs/TECH_SPEC.md](docs/TECH_SPEC.md).

## Features

- Collect messages from Telegram channels
- Categorize messages by topic
- Generate digests with summaries
- Publish digests to Telegram, email, and web
- Admin interface for managing digests, sources, topics, and users
- Web interface for viewing published digests

## Monitoring

Logging is provided via **structlog** in JSON format. Prometheus metrics such as `ingest_posts_total` and `summary_latency_seconds` are exposed together with a `/health` endpoint by `app.common.metrics.start_metrics_server`.

Alerting helpers in `app.common.alerts` emit structured log events for situations like master session invalidation, LLM circuit breaker activation, digest publication failures, and empty digest releases.

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Create a `.env` file with the following variables:

```
# Telegram API credentials
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_PHONE=your_phone_number

# Database configuration
DATABASE_URL=sqlite:///mg.db

# Web server configuration
WEB_HOST=0.0.0.0
WEB_PORT=8000

# Telegram publishing
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHANNEL_ID=your_channel_id

# Email publishing
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your_email@example.com
SMTP_PASSWORD=your_password

# Component enablement
ENABLE_WATCHER=true
ENABLE_SCHEDULER=true
ENABLE_WEB=true
```

## Usage

### Running Individual Components

To run the Telegram watcher:

```bash
python -m app.watcher
```

To run the scheduler:

```bash
python run_scheduler.py
```

To run the web server:

```bash
python run_web.py
```

### Running All Components

To run all components at once:

```bash
python run_all.py
```

## Web Interface

The web interface is available at http://localhost:8000 (or the host and port specified in your configuration).

### Public Interface

- `/` - Home page
- `/digests` - List of published digests
- `/digests/{digest_id}` - View a specific digest
- `/about` - About page

### Admin Interface

- `/admin` - Admin dashboard
- `/admin/digests` - Manage digests
- `/admin/sources` - Manage sources
- `/admin/topics` - Manage topics
- `/admin/users` - Manage users

## API

### Public API

- `GET /api/digests` - Get all published digests
- `GET /api/digests/{digest_id}` - Get a specific published digest
- `GET /api/digests/{digest_id}/items` - Get items for a specific published digest

### Admin API

- `GET /api/admin/digests` - Get all digests
- `GET /api/admin/digests/{digest_id}` - Get a specific digest
- `POST /api/admin/digests` - Create a new digest
- `PUT /api/admin/digests/{digest_id}` - Update a digest
- `DELETE /api/admin/digests/{digest_id}` - Delete a digest
- `POST /api/admin/digests/{digest_id}/publish` - Publish a digest

- `GET /api/admin/sources` - Get all sources
- `GET /api/admin/sources/{source_id}` - Get a specific source
- `POST /api/admin/sources` - Create a new source
- `PUT /api/admin/sources/{source_id}` - Update a source
- `DELETE /api/admin/sources/{source_id}` - Delete a source

- `GET /api/admin/topics` - Get all topics
- `GET /api/admin/topics/{topic_id}` - Get a specific topic
- `POST /api/admin/topics` - Create a new topic
- `PUT /api/admin/topics/{topic_id}` - Update a topic
- `DELETE /api/admin/topics/{topic_id}` - Delete a topic

- `GET /api/admin/users` - Get all users
- `GET /api/admin/users/{user_id}` - Get a specific user
- `POST /api/admin/users` - Create a new user
- `PUT /api/admin/users/{user_id}` - Update a user
- `DELETE /api/admin/users/{user_id}` - Delete a user
