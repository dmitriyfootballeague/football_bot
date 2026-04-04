.PHONY: up up-scraper down build restart logs ps migrate shell-bot shell-db test-bot test-scraper

VENV_SITE_PACKAGES := $(shell ls -d .venv/lib/python*/site-packages 2>/dev/null | head -n 1)

up:
	docker compose up -d

up-scraper:
	docker compose up -d postgres scraper

down:
	docker compose down

logs-bot:
	docker compose logs -f tg_bot

logs-scraper:
	docker compose logs -f scraper

migrate:
	docker compose exec tg_bot alembic upgrade head

shell-bot:
	docker compose exec tg_bot bash

shell-db:
	docker compose exec postgres psql -U $${POSTGRES_USERNAME} -d $${POSTGRES_DB}

test-scraper:
	@if [ -n "$(VENV_SITE_PACKAGES)" ]; then \
		PYTHONPATH="$(VENV_SITE_PACKAGES)" python3 -m pytest tests/scraper; \
	else \
		python3 -m pytest tests/scraper; \
	fi

test-bot:
	@if [ -n "$(VENV_SITE_PACKAGES)" ]; then \
		PYTHONPATH="$(VENV_SITE_PACKAGES)" python3 -m pytest tests/football_bot; \
	else \
		python3 -m pytest tests/football_bot; \
	fi
