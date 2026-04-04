#!/usr/bin/env bash

set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting bot..."
exec python -m football_bot
