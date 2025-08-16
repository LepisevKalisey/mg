# Deployment Configuration Guide

This document outlines the deployment configurations for the mg-digest-bot project across different platforms and methods.

## Python Version Consistency
- **Python Version**: 3.11.x
- **Configuration Files**:
  - `runtime.txt`: `python-3.11`
  - `pyproject.toml`: `requires-python = ">=3.11"`
  - `nixpacks.toml`: Uses `python311` packages

## Deployment Methods

### 1. Coolify with Nixpacks
**Primary Configuration**: `nixpacks.toml`
- **Service**: Main web service (bot)
- **Command**: `python run_web.py`
- **Port**: 8000

**Additional Configurations**:
- `nixpacks.watcher.toml`: For watcher service
- `nixpacks.worker.toml`: For worker service

### 2. Docker Compose
**Configuration**: `docker-compose.yml`
- **Services**: bot, watcher, worker, scheduler, db, redis
- **Base Image**: `python:3.11-slim`
- **Environment Variables**: Defined in docker-compose.yml

### 3. Dockerfiles
- `bot.Dockerfile`: For main bot service
- `watcher.Dockerfile`: For watcher service
- `worker.Dockerfile`: For worker service

## Environment Variables

### Required Variables
```bash
# Database
DATABASE_URL=postgresql://user:password@host:port/database

# Redis
REDIS_URL=redis://localhost:6379

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash

# LLM Services
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
```

### Optional Variables
```bash
PORT=8000
PYTHONUNBUFFERED=1
PYTHONPATH=/app
```

## Deployment Steps

### Coolify Deployment
1. Configure environment variables in Coolify
2. Select appropriate Nixpacks configuration:
   - Use `nixpacks.toml` for main web service
   - Use `nixpacks.watcher.toml` for watcher service
   - Use `nixpacks.worker.toml` for worker service
3. Ensure database and Redis services are available
4. Deploy

### Docker Compose Deployment
1. Copy environment variables to `.env` file
2. Run: `docker-compose up -d`
3. Check logs: `docker-compose logs -f`

## Health Checks

### Web Service
- **Endpoint**: `/health`
- **Port**: 8000
- **Response**: JSON with service status

### Database
- **Check**: PostgreSQL connection
- **Command**: `python -c "import psycopg2; psycopg2.connect()"`

### Redis
- **Check**: Redis connection
- **Command**: `python -c "import redis; redis.Redis().ping()"`

## Troubleshooting

### Common Issues
1. **Python version mismatch**: Ensure all configs use Python 3.11
2. **Missing dependencies**: Check requirements.txt and Nixpacks packages
3. **Database connection**: Verify DATABASE_URL format
4. **Redis connection**: Verify REDIS_URL format

### Debug Commands
```bash
# Check Python version
python --version

# Check installed packages
pip list

# Test database connection
python -c "import psycopg2; print('PostgreSQL OK')"

# Test Redis connection
python -c "import redis; print('Redis OK')"
```

## File Structure
```
mg/
├── nixpacks.toml          # Main Nixpacks config
├── nixpacks.watcher.toml  # Watcher service config
├── nixpacks.worker.toml   # Worker service config
├── runtime.txt           # Python version
├── pyproject.toml        # Python project config
├── requirements.txt      # Python dependencies
├── Procfile             # Heroku-style process definitions
├── docker-compose.yml   # Docker Compose configuration
├── bot.Dockerfile       # Bot service Dockerfile
├── watcher.Dockerfile   # Watcher service Dockerfile
├── worker.Dockerfile    # Worker service Dockerfile
├── .dockerignore        # Docker ignore patterns
└── DEPLOYMENT.md        # This file
```