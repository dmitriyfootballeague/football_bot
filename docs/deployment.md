# Deployment

This repository includes a GitHub Actions workflow that can automatically deploy the project to a Linux server over SSH.

## Deployment model

The workflow does two things:

1. Runs the test suite on GitHub Actions.
2. Connects to the server over SSH and runs `scripts/deploy.sh`.

The deployment script updates the checked-out repository on the server and then runs:

```bash
docker compose up -d --build --remove-orphans
```

This means the server builds the bot and scraper images locally from the repository checkout.

## Files

- `.github/workflows/deploy.yml`
- `scripts/deploy.sh`

## Server preparation

Prepare the Linux server once:

1. Install Docker Engine and Docker Compose plugin.
2. Clone this repository onto the server.
3. Create the production `.env` file in the project root.
4. Make sure the SSH user used by GitHub Actions:
   - can access the repository directory
   - can run `docker compose`
   - can pull updates from GitHub inside the server checkout

Example:

```bash
git clone git@github.com:dmitriyfootballeague/football_bot.git /opt/football_bot
cd /opt/football_bot
cp .env.example .env
chmod +x scripts/deploy.sh
docker compose up -d --build
```

If the repository on the server is private, configure a deploy key or another non-interactive Git credential method for that server checkout.

## GitHub setup

Create these repository secrets in GitHub:

- `DEPLOY_HOST` - server IP or hostname
- `DEPLOY_USER` - SSH user
- `DEPLOY_SSH_KEY` - private SSH key used by GitHub Actions
- `DEPLOY_APP_DIR` - absolute path to the app on the server, for example `/opt/football_bot`
- `DEPLOY_PORT` - optional, defaults to `22`
- `DEPLOY_BRANCH` - optional, defaults to `main`

It is also a good idea to create a GitHub Actions environment named `production` and keep the deploy secrets there.

## Branch behavior

The workflow deploys automatically on pushes to `main`.

If you want a different branch:

- change the `on.push.branches` list in `.github/workflows/deploy.yml`
- or store a different value in `DEPLOY_BRANCH`

For this repository, the current local branch is not `main`, so update the workflow if your default deployment branch is different.

## Notes

- The deploy script uses `git pull --ff-only`, so it will fail instead of overwriting local server changes.
- Database migrations run automatically because both container entrypoints call `alembic upgrade head`.
- The server must already have a valid `.env` file before the first deploy.
