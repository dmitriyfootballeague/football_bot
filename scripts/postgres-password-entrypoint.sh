#!/bin/sh

set -eu

SYNC_FLAG="/tmp/postgres-password-synced"

cleanup() {
    if [ -n "${pg_pid:-}" ] && kill -0 "${pg_pid}" 2>/dev/null; then
        kill "${pg_pid}" 2>/dev/null || true
    fi
}

rm -f "${SYNC_FLAG}"
trap cleanup INT TERM

/usr/local/bin/docker-entrypoint.sh "$@" &
pg_pid=$!

if [ "${1:-}" = "postgres" ]; then
    tries=0
    until pg_isready -h 127.0.0.1 -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-postgres}" >/dev/null 2>&1; do
        tries=$((tries + 1))

        if ! kill -0 "${pg_pid}" 2>/dev/null; then
            wait "${pg_pid}"
            exit $?
        fi

        if [ "${tries}" -ge 120 ]; then
            echo "Timed out waiting for PostgreSQL TCP startup" >&2
            kill "${pg_pid}" 2>/dev/null || true
            wait "${pg_pid}" || true
            exit 1
        fi

        sleep 1
    done

    if [ -z "${POSTGRES_USER:-}" ] || [ -z "${POSTGRES_PASSWORD:-}" ]; then
        echo "POSTGRES_USER and POSTGRES_PASSWORD must be set" >&2
        kill "${pg_pid}" 2>/dev/null || true
        wait "${pg_pid}" || true
        exit 1
    fi

    psql \
        -v ON_ERROR_STOP=1 \
        -h 127.0.0.1 \
        -U "${POSTGRES_USER}" \
        -d postgres \
        -v role_name="${POSTGRES_USER}" \
        -v role_password="${POSTGRES_PASSWORD}" <<'SQL'
SET password_encryption = 'scram-sha-256';
SELECT format(
  'ALTER ROLE %I WITH PASSWORD %L',
  :'role_name',
  :'role_password'
) \gexec
SQL

    touch "${SYNC_FLAG}"
fi

wait "${pg_pid}"
