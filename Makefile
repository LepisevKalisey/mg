COMPOSE := docker compose -f docker/docker-compose.yml
DATABASE_URL ?= sqlite:///app.db

.PHONY: up down logs migrate seed test e2e

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

migrate:
	DATABASE_URL=$(DATABASE_URL) alembic upgrade head

seed:
	DATABASE_URL=$(DATABASE_URL) python -m app.db.seed

test:
	pytest

e2e:
	pytest -m e2e
