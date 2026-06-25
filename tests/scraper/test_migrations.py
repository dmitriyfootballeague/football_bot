import builtins
import importlib.util
from pathlib import Path
from types import SimpleNamespace


MIGRATION_007_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "007_fixed_player_positions.py"
)


def _load_migration_007():
    spec = importlib.util.spec_from_file_location(
        "alembic_revision_007_test",
        MIGRATION_007_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeBind:
    def __init__(self):
        self.dialect = SimpleNamespace(name="sqlite")
        self.executed: list[tuple[str, dict[str, str]]] = []

    def execute(self, stmt, params):
        self.executed.append((str(stmt), params))


class FakeOp:
    def __init__(self, bind):
        self.bind = bind
        self.added_columns: list[tuple[str, str]] = []

    def get_bind(self):
        return self.bind

    def add_column(self, table_name, column):
        self.added_columns.append((table_name, column.name))


def test_migration_007_upgrade_uses_embedded_position_snapshot(monkeypatch):
    module = _load_migration_007()
    bind = FakeBind()
    fake_op = FakeOp(bind)
    monkeypatch.setattr(module, "op", fake_op)

    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "scraper.player_position_overrides":
            raise AssertionError("migration must not import runtime position overrides")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    params = module._iter_fixed_player_position_params()
    module.upgrade()

    assert params
    assert params[0] == {
        "external_id": "62ffbb0eaa8c2e49e5f803ba",
        "position": "attacking_midfielder",
    }
    assert fake_op.added_columns == [("scraped_player_stats", "position")]
    assert len(bind.executed) == len(params) * 2
    assert bind.executed[0][1] == params[0]
