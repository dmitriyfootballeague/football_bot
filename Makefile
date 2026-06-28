.PHONY: up up-scraper build-scraper down build restart logs ps migrate shell-bot shell-db test-bot test-bot-unit test-bot-smoke test-bot-e2e test-scraper test-scraper-unit

VENV_SITE_PACKAGES := $(shell ls -d .venv/lib/python*/site-packages 2>/dev/null | head -n 1)

up:
	docker compose up --build migrate
	docker compose up -d --build --remove-orphans postgres redis tg_bot scraper

build-scraper:
	docker compose build scraper

up-scraper:
	docker compose up -d --build scraper

down:
	docker compose down

migrate:
	docker compose exec tg_bot alembic upgrade head

shell-db:
	docker compose exec postgres psql -U $${POSTGRES_USERNAME} -d $${POSTGRES_DB}

test-scraper: test-scraper-unit

test-scraper-unit:
	@if [ -n "$(VENV_SITE_PACKAGES)" ]; then \
		PYTHONPATH="$(VENV_SITE_PACKAGES)" python3 -m pytest tests/scraper/unit; \
	else \
		python3 -m pytest tests/scraper/unit; \
	fi

test-bot: test-bot-unit test-bot-smoke

test-bot-unit:
	@if [ -n "$(VENV_SITE_PACKAGES)" ]; then \
		PYTHONPATH="$(VENV_SITE_PACKAGES)" python3 -m pytest tests/football_bot/unit; \
	else \
		python3 -m pytest tests/football_bot/unit; \
	fi

test-bot-smoke:
	@if [ -n "$(VENV_SITE_PACKAGES)" ]; then \
		PYTHONPATH="$(VENV_SITE_PACKAGES)" python3 -m pytest tests/football_bot/smoke; \
	else \
		python3 -m pytest tests/football_bot/smoke; \
	fi

test-bot-e2e:
	@if [ -n "$(VENV_SITE_PACKAGES)" ]; then \
		RUN_REAL_E2E_TESTS=1 PYTHONPATH="$(VENV_SITE_PACKAGES)" python3 -m pytest -m e2e tests/football_bot/e2e; \
	else \
		RUN_REAL_E2E_TESTS=1 python3 -m pytest -m e2e tests/football_bot/e2e; \
	fi
