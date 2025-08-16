DATABASE_URL ?= sqlite:///app.db

.PHONY: migrate seed test e2e

migrate:
	DATABASE_URL=$(DATABASE_URL) alembic upgrade head

seed:
	DATABASE_URL=$(DATABASE_URL) python -m app.db.seed

test:
	pytest

e2e:
	pytest -m e2e
