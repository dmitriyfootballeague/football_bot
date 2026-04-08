# Football Bot

Telegram bot for the MSU amateur football league. The project manages player registration, ratings, and club transfer workflows, and includes a separate scraper service that syncs tournament and player data from `olesports.ru`.

## What the project does

- Player registration with admin approval or rejection
- Role-based bot experience for players, captains, and free agents
- Rating screens for current season and previous season
- Transfer workflows with captain and admin decision steps
- Admin panel for editing club names and player ratings
- Periodic scraping of tournaments, clubs, and player stats into PostgreSQL

## Main user flows

### Registration

New users start from `/start`, open the registration flow, provide profile data, upload a photo, and choose whether they are joining a club or registering as a free agent. Submitted applications go to admins for moderation.

### Ratings

Approved players and captains can view their current rating. Free agents can view previous-season rating data. Rating values can also be edited manually from the admin panel.

### Transfers

The bot supports several transfer scenarios:

- player leaves a club and becomes a free agent
- player requests to join another club
- captain invites a free agent to the club
- captain removes a player from the club

Depending on the scenario, the flow may require captain approval, player confirmation, and final admin approval.

### Admin operations

Admins can:

- approve or reject registrations
- approve or reject transfer requests
- update club names
- update current and previous-season ratings

## Project structure

The code follows a layered layout:

- `football_bot/handlers` - Telegram handlers and FSM flows
- `football_bot/service` - business logic
- `football_bot/repository` - data access layer
- `football_bot/models` - SQLAlchemy models
- `football_bot/keyboards` - reply and inline keyboards
- `football_bot/locales/messages.py` - user-facing text
- `scraper/` - Playwright-based scraping and sync logic
- `alembic/` - database migrations
- `tests/` - automated and manual QA coverage

## Tech stack

- Python 3.12
- aiogram 3
- SQLAlchemy 2 + asyncpg
- Alembic
- PostgreSQL
- Redis
- Playwright
- Docker Compose

## Services

`docker-compose.yml` defines four services:

- `postgres` - main database
- `redis` - FSM storage for production-like runs
- `tg_bot` - Telegram bot process
- `scraper` - periodic sync service

The bot uses long polling. In local development, it can run without Redis by setting `USE_REDIS=False`, which switches FSM storage to in-memory storage.

## Environment configuration

Create a `.env` file in the project root. You can use `.env.example` as the starting point and extend it with any deployment-specific values you need.

```env
BOT_TOKEN=your_telegram_bot_token
ADMIN_IDS=123456789
LEAGUE_ADMIN_IDS=123456789

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USERNAME=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=football_bot

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
USE_REDIS=False

SCRAPE_URL=https://olesports.ru/tournament/68fba38cd56d2ba191d6eaee
SYNC_INTERVAL_HOURS=6
SCRAPER_ALLOWED_TOURNAMENTS=
SCRAPER_PLAYER_TOURNAMENT=
```

Notes:

- `ADMIN_IDS` and `LEAGUE_ADMIN_IDS` are comma-separated Telegram user IDs.
- Empty `SCRAPER_ALLOWED_TOURNAMENTS` means "scrape all discovered tournaments".
- `SCRAPER_PLAYER_TOURNAMENT` can be used to target an exact player-stat tournament label.
- Database migrations are handled by a dedicated Compose `migrate` service.

## Recommended development setup

Docker Compose is the simplest and most reliable setup because it matches the intended runtime, includes PostgreSQL and Redis, and already handles scraper dependencies.

### Start full stack

```bash
docker compose up --build
```

Or, after the initial build:

```bash
make up
```

Useful commands:

```bash
make logs-bot
make logs-scraper
make migrate
make shell-bot
make shell-db
make down
```

### Start only database and scraper

```bash
make up-scraper
```

## Local development without Docker

If you want to run the bot directly on your machine:

1. Create and activate a Python 3.12 virtual environment.
2. Install bot dependencies:

```bash
pip install -r requirements.txt
```

3. If you also want to run the scraper locally, install scraper dependencies and Playwright browser binaries:

```bash
pip install -r requirements.scraper.txt
playwright install chromium
```

4. Start PostgreSQL locally and create the database defined in `.env`.
5. Run migrations:

```bash
alembic upgrade head
```

6. Start the bot:

```bash
python -m football_bot
```

7. Start the scraper in a separate terminal if needed:

```bash
python -m scraper
```

Local notes:

- Redis is optional for the bot if `USE_REDIS=False`.
- The scraper still requires PostgreSQL.
- Docker is still the better choice when debugging Playwright or deployment-specific issues.

## Tests and QA

Run automated tests with:

```bash
make test-bot
make test-scraper
```

Manual verification checklist:

- `tests/qa/manual_qa_checklist.md`

The manual checklist covers registration, instructions, ratings, transfers, admin actions, and regression scenarios.

## Deployment notes

The current project is already set up for containerized deployment:

1. Provide a production `.env`.
2. Run `docker compose up --build migrate`.
3. Run `docker compose up -d --build`.
4. Verify container health and logs.

Operational details:

- database migrations run through the dedicated `migrate` service
- bot state storage should use Redis in deployed environments
- scraper sync interval is controlled by `SYNC_INTERVAL_HOURS`
- PostgreSQL and Redis data are persisted with Docker volumes

## CI/CD

The repository includes a GitHub Actions deployment workflow:

- workflow file: `.github/workflows/deploy.yml`
- server deploy script: `scripts/deploy.sh`
- setup guide: `docs/deployment.md`

The default behavior is:

- run tests on GitHub Actions
- on push to `main`, connect to the Linux server over SSH
- pull the latest code in the server checkout
- run the `migrate` service once
- start the long-lived services with `docker compose up -d --build --remove-orphans postgres redis tg_bot scraper`

## Additional repository notes

- Main specification: `tech_task.pdf` (Russian)
- Architecture reference for contributors: `CONTEXT.md`
- User-facing strings are centralized in `football_bot/locales/messages.py`
