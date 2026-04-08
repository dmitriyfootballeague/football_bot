#!/usr/bin/env bash

set -euo pipefail

APP_DIR="${DEPLOY_APP_DIR:-$(pwd)}"
BRANCH="${DEPLOY_BRANCH:-main}"

echo "Deploying branch '${BRANCH}' in '${APP_DIR}'"

if [ ! -d "${APP_DIR}" ]; then
    echo "APP_DIR does not exist: ${APP_DIR}" >&2
    exit 1
fi

cd "${APP_DIR}"

if [ ! -d .git ]; then
    echo "No git repository found in ${APP_DIR}" >&2
    exit 1
fi

git fetch origin "${BRANCH}"
git checkout "${BRANCH}"
git pull --ff-only origin "${BRANCH}"

docker compose up -d --build --remove-orphans

echo "Deployment finished successfully."
