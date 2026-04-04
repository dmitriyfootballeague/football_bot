# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telegram bot for the MSU amateur football league ("Scout MSU Liga"). Manages player registration, ratings, and transfers between clubs. Full specification is in `tech_task.pdf` (in Russian) — use it as the primary reference for all features and notification texts.

## Tech Stack

- **Python 3.12**, **aiogram 3.x** (async Telegram bot framework)
- **SQLAlchemy 2.x** with async engine (`asyncpg`), **Alembic** for migrations
- **PostgreSQL 16** + **Redis 7** (FSM storage)
- **Playwright** for scraping league data from olesports.ru (React SPA)
- **Docker Compose** for deployment

## Commands

```bash
# Run with Docker
docker compose up --build

# Run locally (requires .env with all vars from .env.example)
python -m football_bot

# Alembic migrations
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Architecture

Layered architecture: handlers -> service -> repository -> models.

- `football_bot/__main__.py` — Entry point. Wires Bot, Dispatcher, routers, middleware, workflow_data, and background scraper task.
- `handlers/commands.py` — /start, /help, /cancel commands
- `handlers/user/registration_handlers.py` — Full FSM registration flow (10 states)
- `handlers/user/rating_handlers.py` — "Рейтинг" and "Рейтинг за прошлый сезон" display
- `handlers/user/instruction_handler.py` — "Инструкция" button handler
- `handlers/admin/admin_handlers.py` — Registration approve/reject callbacks
- `keyboards/inline/` — Callback keyboards (start, registration steps, admin actions)
- `keyboards/reply/` — Role-based persistent menus (player, free agent, captain)
- `states/registration.py` — `FSMRegistration` StatesGroup with 10 states
- `filters/` — `IsAdminFilter`, `IsLeagueAdminFilter`, name/date validators
- `middlewares/db_middleware.py` — Injects `AsyncSession` into handlers via `data["session"]`
- `models/` — SQLAlchemy ORM: `Player`, `Club`, `Tournament` with enums (`PlayerRole`, `PlayerPosition`, `RegistrationStatus`)
- `repository/` — Data access: `PlayerRepository`, `ClubRepository`, `TournamentRepository`
- `service/` — Business logic: `RegistrationService`, `RatingService`
- `scraper/league_scraper.py` — Playwright-based scraper (selectors need refinement on live DOM)
- `scraper/sync_service.py` — Background periodic sync (every 6h)
- `locales/messages.py` — All user-facing strings from tech_task.pdf
- `db/postgres/resource.py` — `create_pool()` returns `async_sessionmaker`
- `utils/config.py` — Dataclass configs: `BotConfig`, `DBConfig`, `RedisConfig`

## Key Patterns

- Handlers receive `session: AsyncSession` automatically via middleware.
- Admin IDs passed via `dp.workflow_data` as `admin_ids: list` and `league_admin_ids: list`.
- FSM storage: Redis in production (`USE_REDIS=True`), MemoryStorage for local dev.
- All user-facing text lives in `locales/messages.py` — never hardcode Russian strings in handlers.
- Keyboards use `CallbackData` subclasses for type-safe callback parsing (`TournamentCallback`, `ClubCallback`, `PositionCallback`, `AdminRegAction`).

## Data Source

Player ratings and match statistics scraped from:
https://olesports.ru/tournament/68fba38cd56d2ba191d6eaee

The scraper CSS selectors are skeleton — they need refinement by inspecting the live rendered DOM.
