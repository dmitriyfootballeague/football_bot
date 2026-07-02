#!/bin/sh

set -eu

SYNC_FLAG="/tmp/postgres-password-synced"
PGDATA_DIR="${PGDATA:-/var/lib/postgresql/data}"

sql_quote_literal() {
    escaped=$(printf "%s" "$1" | sed "s/'/''/g")
    printf "'%s'" "${escaped}"
}

sql_quote_identifier() {
    escaped=$(printf "%s" "$1" | sed 's/"/""/g')
    printf '"%s"' "${escaped}"
}

run_as_postgres() {
    if command -v su-exec >/dev/null 2>&1; then
        su-exec postgres "$@"
        return
    fi

    if command -v gosu >/dev/null 2>&1; then
        gosu postgres "$@"
        return
    fi

    echo "Neither su-exec nor gosu is available to run postgres maintenance commands" >&2
    exit 1
}

cleanup() {
    if [ -n "${pg_pid:-}" ] && kill -0 "${pg_pid}" 2>/dev/null; then
        kill "${pg_pid}" 2>/dev/null || true
    fi
}

start_postgres() {
    /usr/local/bin/docker-entrypoint.sh "$@" &
    pg_pid=$!
}

stop_postgres() {
    if [ -n "${pg_pid:-}" ] && kill -0 "${pg_pid}" 2>/dev/null; then
        kill "${pg_pid}" 2>/dev/null || true
        wait "${pg_pid}" || true
    fi
}

wait_for_postgres() {
    tries=0
    until pg_isready -h 127.0.0.1 -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-postgres}" >/dev/null 2>&1; do
        tries=$((tries + 1))

        if ! kill -0 "${pg_pid}" 2>/dev/null; then
            wait "${pg_pid}"
            exit $?
        fi

        if [ "${tries}" -ge 120 ]; then
            echo "Timed out waiting for PostgreSQL TCP startup" >&2
            stop_postgres
            exit 1
        fi

        sleep 1
    done
}

sync_role_password() {
    psql \
        -v ON_ERROR_STOP=1 \
        -h 127.0.0.1 \
        -U "${POSTGRES_USER}" \
        -d template1 \
        -v role_name="${POSTGRES_USER}" \
        -v role_password="${POSTGRES_PASSWORD}" <<'SQL'
SET password_encryption = 'scram-sha-256';
SELECT format(
  'ALTER ROLE %I WITH LOGIN PASSWORD %L',
  :'role_name',
  :'role_password'
) \gexec
SQL
}

repair_role_with_single_user() {
    role_ident=$(sql_quote_identifier "${POSTGRES_USER}")
    role_password=$(sql_quote_literal "${POSTGRES_PASSWORD}")

    echo "Repairing role ${POSTGRES_USER} in single-user mode" >&2

    printf "SET password_encryption = 'scram-sha-256';\nALTER ROLE %s WITH LOGIN PASSWORD %s;\n" \
        "${role_ident}" "${role_password}" \
        | run_as_postgres postgres --single -D "${PGDATA_DIR}" template1 >/dev/null
}

rm -f "${SYNC_FLAG}"
trap cleanup INT TERM

start_postgres "$@"

if [ "${1:-}" = "postgres" ]; then
    if [ -z "${POSTGRES_USER:-}" ] || [ -z "${POSTGRES_PASSWORD:-}" ]; then
        echo "POSTGRES_USER and POSTGRES_PASSWORD must be set" >&2
        stop_postgres
        exit 1
    fi

    wait_for_postgres

    psql_output="$(mktemp)"
    if ! sync_role_password >"${psql_output}" 2>&1; then
        cat "${psql_output}" >&2

        if grep -q "not permitted to log in" "${psql_output}"; then
            stop_postgres
            repair_role_with_single_user
            start_postgres "$@"
            wait_for_postgres
            sync_role_password
        else
            stop_postgres
            rm -f "${psql_output}"
            exit 1
        fi
    fi
    rm -f "${psql_output}"

    touch "${SYNC_FLAG}"
fi

wait "${pg_pid}"
