.PHONY: up up-scraper down build restart logs ps migrate shell-bot shell-db test-bot test-scraper

VENV_SITE_PACKAGES := $(shell ls -d .venv/lib/python*/site-packages 2>/dev/null | head -n 1)

up:
	docker compose up --build migrate
	docker compose up -d --build --remove-orphans postgres redis tg_bot scraper

down:
	docker compose down

migrate:
	docker compose exec tg_bot alembic upgrade head

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
