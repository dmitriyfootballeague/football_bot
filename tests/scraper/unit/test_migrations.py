import builtins
import importlib.util
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace


MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "alembic" / "versions"


def _load_migration(filename: str):
    spec = importlib.util.spec_from_file_location(
        f"alembic_revision_{filename.removesuffix('.py')}_test",
        MIGRATIONS_DIR / filename,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeBind:
    def __init__(self, dialect_name: str = "sqlite"):
        self.dialect = SimpleNamespace(name=dialect_name)
        self.executed: list[tuple[str, dict[str, str] | None]] = []

    def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))


class FakeInspector:
    def __init__(self, tables=None, columns=None, indexes=None):
        self._tables = list(tables or [])
        self._columns = columns or {}
        self._indexes = indexes or {}

    def get_table_names(self):
        return list(self._tables)

    def get_columns(self, table_name):
        return list(self._columns.get(table_name, []))

    def get_indexes(self, table_name):
        return list(self._indexes.get(table_name, []))


class FakeOp:
    def __init__(self, bind):
        self.bind = bind
        self.added_columns: list[tuple[str, str]] = []
        self.dropped_columns: list[tuple[str, str]] = []
        self.created_tables: list[str] = []
        self.created_indexes: list[tuple[str, str, tuple[str, ...], bool]] = []
        self.renamed_tables: list[tuple[str, str]] = []
        self.altered_columns: list[tuple[str, str, str | None]] = []
        self.executed_sql: list[str] = []

    def get_bind(self):
        return self.bind

    def get_context(self):
        return SimpleNamespace(autocommit_block=lambda: nullcontext())

    def add_column(self, table_name, column):
        self.added_columns.append((table_name, column.name))

    def drop_column(self, table_name, column_name):
        self.dropped_columns.append((table_name, column_name))

    def create_table(self, table_name, *args, **kwargs):
        self.created_tables.append(table_name)

    def create_index(self, index_name, table_name, columns, unique=False):
        self.created_indexes.append((index_name, table_name, tuple(columns), unique))

    def rename_table(self, old_name, new_name):
        self.renamed_tables.append((old_name, new_name))

    def alter_column(self, table_name, column_name, new_column_name=None, **kwargs):
        self.altered_columns.append((table_name, column_name, new_column_name))

    def execute(self, sql):
        self.executed_sql.append(str(sql))


def test_migration_007_upgrade_uses_embedded_position_snapshot(monkeypatch):
    module = _load_migration("007_fixed_player_positions.py")
    bind = FakeBind()
    fake_op = FakeOp(bind)
    inspector = FakeInspector(
        tables=["scraped_player_stats", "players"],
        columns={"scraped_player_stats": []},
    )
    monkeypatch.setattr(module, "op", fake_op)
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: inspector)

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


def test_migration_007_upgrade_skips_add_column_if_position_already_exists(monkeypatch):
    module = _load_migration("007_fixed_player_positions.py")
    bind = FakeBind()
    fake_op = FakeOp(bind)
    inspector = FakeInspector(
        tables=["scraped_player_stats", "players"],
        columns={"scraped_player_stats": [{"name": "id"}, {"name": "position"}]},
    )
    monkeypatch.setattr(module, "op", fake_op)
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: inspector)

    module.upgrade()

    assert fake_op.added_columns == []
    assert bind.executed


def test_migration_004_upgrade_skips_existing_schema_bits(monkeypatch):
    module = _load_migration("004_scraped_player_stats.py")
    bind = FakeBind()
    fake_op = FakeOp(bind)
    inspector = FakeInspector(
        tables=["players", "scraped_player_stats"],
        columns={"players": [{"name": "id"}, {"name": "external_id"}]},
        indexes={
            "players": [{"name": "ix_players_external_id"}],
            "scraped_player_stats": [
                {"name": "ix_scraped_player_stats_external_id"},
                {"name": "ix_scraped_player_stats_club_id"},
            ],
        },
    )
    monkeypatch.setattr(module, "op", fake_op)
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: inspector)

    module.upgrade()

    assert fake_op.added_columns == []
    assert fake_op.created_tables == []
    assert fake_op.created_indexes == []


def test_migration_005_upgrade_skips_when_rename_already_applied(monkeypatch):
    module = _load_migration("005_rename_divisions_to_tournaments.py")
    bind = FakeBind()
    fake_op = FakeOp(bind)
    inspector = FakeInspector(
        tables=["tournaments", "clubs"],
        columns={"clubs": [{"name": "id"}, {"name": "tournament_id"}]},
    )
    monkeypatch.setattr(module, "op", fake_op)
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: inspector)

    module.upgrade()

    assert fake_op.renamed_tables == []
    assert fake_op.altered_columns == []


def test_migration_006_upgrade_skips_existing_column(monkeypatch):
    module = _load_migration("006_prev_rating_updated_at.py")
    bind = FakeBind()
    fake_op = FakeOp(bind)
    inspector = FakeInspector(
        tables=["players"],
        columns={"players": [{"name": "id"}, {"name": "prev_rating_updated_at"}]},
    )
    monkeypatch.setattr(module, "op", fake_op)
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: inspector)

    module.upgrade()

    assert fake_op.added_columns == []


def test_migration_008_upgrade_skips_existing_table_and_indexes(monkeypatch):
    module = _load_migration("008_match_stats.py")
    bind = FakeBind()
    fake_op = FakeOp(bind)
    inspector = FakeInspector(
        tables=["match_stats"],
        indexes={
            "match_stats": [
                {"name": "ix_match_stats_match_external_id"},
                {"name": "ix_match_stats_player_external_id"},
            ],
        },
    )
    monkeypatch.setattr(module, "op", fake_op)
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: inspector)

    module.upgrade()

    assert fake_op.created_tables == []
    assert fake_op.created_indexes == []


def test_migration_009_upgrade_adds_kick_enum_value(monkeypatch):
    module = _load_migration("009_add_kick_transfer_type.py")
    bind = FakeBind(dialect_name="postgresql")
    fake_op = FakeOp(bind)
    monkeypatch.setattr(module, "op", fake_op)

    module.upgrade()

    assert fake_op.executed_sql == [
        "ALTER TYPE transfertype ADD VALUE IF NOT EXISTS 'kick'"
    ]


def test_migration_010_upgrade_skips_existing_rating_columns(monkeypatch):
    module = _load_migration("010_scraped_player_ratings.py")
    bind = FakeBind()
    fake_op = FakeOp(bind)
    inspector = FakeInspector(
        tables=["scraped_player_stats"],
        columns={
            "scraped_player_stats": [
                {"name": "id"},
                {"name": "current_rating"},
                {"name": "division_rank"},
                {"name": "division_total"},
                {"name": "avg_points_per_game"},
            ]
        },
    )
    monkeypatch.setattr(module, "op", fake_op)
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: inspector)

    module.upgrade()

    assert fake_op.added_columns == []


def test_migration_011_upgrade_skips_existing_schema_bits(monkeypatch):
    module = _load_migration("011_player_season_ratings_view.py")
    bind = FakeBind()
    fake_op = FakeOp(bind)
    inspector = FakeInspector(
        tables=["scraped_player_season_stats", "match_stats"],
        columns={
            "match_stats": [
                {"name": "id"},
                {"name": "season_key"},
                {"name": "season_label"},
            ],
        },
        indexes={
            "scraped_player_season_stats": [
                {"name": "ix_scraped_player_season_stats_external_id"},
                {"name": "ix_scraped_player_season_stats_season_key"},
                {"name": "ix_scraped_player_season_stats_season_label"},
                {"name": "ix_scraped_player_season_stats_club_id"},
            ],
            "match_stats": [
                {"name": "ix_match_stats_player_external_id_season_label"},
            ],
        },
    )
    monkeypatch.setattr(module, "op", fake_op)
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: inspector)

    module.upgrade()

    assert fake_op.created_tables == []
    assert fake_op.added_columns == []
    assert fake_op.created_indexes == []
    assert fake_op.executed_sql
    assert any("in_roster" in sql for sql in fake_op.executed_sql)


def test_migration_012_upgrade_skips_existing_override_columns(monkeypatch):
    module = _load_migration("012_rating_overrides_on_season_stats.py")
    bind = FakeBind()
    fake_op = FakeOp(bind)
    inspector = FakeInspector(
        tables=["scraped_player_season_stats"],
        columns={
            "scraped_player_season_stats": [
                {"name": "id"},
                {"name": "rating_override"},
                {"name": "rating_override_updated_at"},
            ]
        },
    )
    monkeypatch.setattr(module, "op", fake_op)
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: inspector)

    module.upgrade()

    assert fake_op.added_columns == []
    assert fake_op.executed_sql
    assert any("in_roster" in sql for sql in fake_op.executed_sql)


def test_migration_013_upgrade_refreshes_view_with_roster_filter(monkeypatch):
    module = _load_migration("013_fix_roster_aware_defensive_points_view.py")
    bind = FakeBind()
    fake_op = FakeOp(bind)
    monkeypatch.setattr(module, "op", fake_op)

    module.upgrade()

    assert fake_op.executed_sql
    assert any("in_roster" in sql for sql in fake_op.executed_sql)


def test_migration_014_upgrade_drops_scraped_snapshot_rating_columns(monkeypatch):
    module = _load_migration("014_drop_scraped_player_rating_columns.py")
    bind = FakeBind()
    fake_op = FakeOp(bind)
    inspector = FakeInspector(
        columns={
            "scraped_player_stats": [
                {"name": "id"},
                {"name": "current_rating"},
                {"name": "division_rank"},
                {"name": "division_total"},
                {"name": "avg_points_per_game"},
            ]
        },
    )
    monkeypatch.setattr(module, "op", fake_op)
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: inspector)

    module.upgrade()

    assert fake_op.dropped_columns == [
        ("scraped_player_stats", "current_rating"),
        ("scraped_player_stats", "division_rank"),
        ("scraped_player_stats", "division_total"),
        ("scraped_player_stats", "avg_points_per_game"),
    ]
