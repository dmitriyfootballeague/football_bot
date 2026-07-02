import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "scripts" / "postgres-password-entrypoint.sh"
DOCKERFILE_POSTGRES = ROOT / "Dockerfile.postgres"
DOCKER_COMPOSE = ROOT / "docker-compose.yml"


def _write_executable(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(0o755)


def _build_wrapper_fixture(
    tmp_path: Path,
    *,
    psql_script: str | None = None,
) -> tuple[Path, Path, Path, Path, Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    sync_flag = tmp_path / "postgres-password-synced"
    fake_entrypoint = tmp_path / "docker-entrypoint.sh"
    psql_args_log = tmp_path / "psql-args.log"
    psql_stdin_log = tmp_path / "psql-stdin.log"
    single_user_args_log = tmp_path / "single-user-args.log"
    single_user_stdin_log = tmp_path / "single-user-stdin.log"

    _write_executable(
        fake_entrypoint,
        "#!/bin/sh\nsleep 0.1\n",
    )
    _write_executable(
        bin_dir / "pg_isready",
        "#!/bin/sh\nexit 0\n",
    )
    _write_executable(
        bin_dir / "psql",
        psql_script
        or (
            "#!/bin/sh\n"
            f"printf '%s\\n' \"$@\" > '{psql_args_log}'\n"
            f"cat > '{psql_stdin_log}'\n"
            "exit 0\n"
        ),
    )
    _write_executable(
        bin_dir / "postgres",
        (
            "#!/bin/sh\n"
            f"printf '%s\\n' \"$@\" > '{single_user_args_log}'\n"
            f"cat > '{single_user_stdin_log}'\n"
            "exit 0\n"
        ),
    )
    _write_executable(
        bin_dir / "su-exec",
        "#!/bin/sh\nshift\nexec \"$@\"\n",
    )

    script_copy = tmp_path / "postgres-password-entrypoint.sh"
    script_copy.write_text(
        SCRIPT_PATH
        .read_text()
        .replace("/usr/local/bin/docker-entrypoint.sh", str(fake_entrypoint))
        .replace("/tmp/postgres-password-synced", str(sync_flag))
    )
    script_copy.chmod(0o755)

    return (
        script_copy,
        sync_flag,
        psql_args_log,
        psql_stdin_log,
        single_user_args_log,
        single_user_stdin_log,
    )


def test_postgres_password_entrypoint_reapplies_password_and_sets_flag(tmp_path):
    (
        script_copy,
        sync_flag,
        psql_args_log,
        psql_stdin_log,
        _single_user_args_log,
        _single_user_stdin_log,
    ) = _build_wrapper_fixture(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path / 'bin'}:{env['PATH']}"
    env["POSTGRES_USER"] = "postgres"
    env["POSTGRES_PASSWORD"] = "postgres"
    env["POSTGRES_DB"] = "postgres"

    result = subprocess.run(
        ["sh", str(script_copy), "postgres"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode == 0
    assert sync_flag.exists()
    assert "-U" in psql_args_log.read_text()
    stdin_sql = psql_stdin_log.read_text()
    assert "SET password_encryption = 'scram-sha-256';" in stdin_sql
    assert "ALTER ROLE" in stdin_sql
    assert "WITH LOGIN PASSWORD" in stdin_sql
    assert "role_password" in stdin_sql


def test_postgres_password_entrypoint_fails_without_password(tmp_path):
    (
        script_copy,
        sync_flag,
        psql_args_log,
        _psql_stdin_log,
        _single_user_args_log,
        _single_user_stdin_log,
    ) = _build_wrapper_fixture(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path / 'bin'}:{env['PATH']}"
    env["POSTGRES_USER"] = "postgres"
    env["POSTGRES_DB"] = "postgres"
    env.pop("POSTGRES_PASSWORD", None)

    result = subprocess.run(
        ["sh", str(script_copy), "postgres"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode == 1
    assert not sync_flag.exists()
    assert not psql_args_log.exists()
    assert "POSTGRES_USER and POSTGRES_PASSWORD must be set" in result.stderr


def test_postgres_password_entrypoint_repairs_nologin_role_with_single_user_mode(tmp_path):
    psql_attempts = tmp_path / "psql-attempts"
    psql_script = (
        "#!/bin/sh\n"
        "attempt=1\n"
        f"if [ -f '{psql_attempts}' ]; then attempt=$(($(cat '{psql_attempts}') + 1)); fi\n"
        f"printf '%s' \"$attempt\" > '{psql_attempts}'\n"
        f"printf '%s\\n' \"$@\" > '{tmp_path / 'psql-args.log'}'\n"
        f"cat > '{tmp_path / 'psql-stdin.log'}'\n"
        "if [ \"$attempt\" -eq 1 ]; then\n"
        "  echo 'psql: error: connection to server at \"127.0.0.1\", port 5432 failed: FATAL:  role \"postgres\" is not permitted to log in' >&2\n"
        "  exit 2\n"
        "fi\n"
        "exit 0\n"
    )
    (
        script_copy,
        sync_flag,
        psql_args_log,
        psql_stdin_log,
        single_user_args_log,
        single_user_stdin_log,
    ) = _build_wrapper_fixture(tmp_path, psql_script=psql_script)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path / 'bin'}:{env['PATH']}"
    env["POSTGRES_USER"] = "postgres"
    env["POSTGRES_PASSWORD"] = "postgres"
    env["POSTGRES_DB"] = "postgres"
    env["PGDATA"] = "/var/lib/postgresql/data/dbfiles"

    result = subprocess.run(
        ["sh", str(script_copy), "postgres"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode == 0
    assert sync_flag.exists()
    assert psql_attempts.read_text() == "2"
    assert "Repairing role postgres in single-user mode" in result.stderr
    assert "--single" in single_user_args_log.read_text()
    single_user_sql = single_user_stdin_log.read_text()
    assert "ALTER ROLE \"postgres\" WITH LOGIN PASSWORD 'postgres';" in single_user_sql
    assert "SET password_encryption = 'scram-sha-256';" in single_user_sql
    assert "-d" in psql_args_log.read_text()
    assert "template1" in psql_args_log.read_text()
    assert "WITH LOGIN PASSWORD" in psql_stdin_log.read_text()


def test_postgres_deployment_files_wire_password_sync():
    dockerfile_text = DOCKERFILE_POSTGRES.read_text()
    compose_text = DOCKER_COMPOSE.read_text()

    assert "COPY scripts/postgres-password-entrypoint.sh" in dockerfile_text
    assert 'ENTRYPOINT ["postgres-password-entrypoint.sh"]' in dockerfile_text
    assert "dockerfile: Dockerfile.postgres" in compose_text
    assert "postgres-password-synced" in compose_text
