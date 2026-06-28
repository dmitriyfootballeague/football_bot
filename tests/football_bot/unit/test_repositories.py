from sqlalchemy.dialects import postgresql

from football_bot.models import RegistrationStatus, TransferStatus, TransferType
from football_bot.repository.club_repo import ClubRepository
from football_bot.repository.player_repo import PlayerRepository
from football_bot.repository.tournament_repo import TournamentRepository
from football_bot.repository.transfer_repo import TransferRepository


class FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        return self.value


class RecordingSession:
    def __init__(self, result=None):
        self.result = result
        self.executed = []
        self.commits = 0
        self.added = []
        self.refreshed = []
        self.get_calls = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        return FakeScalarResult(self.result)

    async def commit(self):
        self.commits += 1

    def add(self, obj):
        self.added.append(obj)

    async def refresh(self, obj):
        self.refreshed.append(obj)

    async def get(self, model, obj_id):
        self.get_calls.append((model, obj_id))
        return self.result


def _sql(stmt):
    return str(stmt.compile(dialect=postgresql.dialect()))


def _params(stmt):
    return stmt.compile(dialect=postgresql.dialect()).params


def test_player_repo_get_pending_registrations_filters_pending(run_async):
    session = RecordingSession(result=[])
    repo = PlayerRepository(session)

    result = run_async(repo.get_pending_registrations())

    assert result == []
    sql = _sql(session.executed[0])
    params = _params(session.executed[0])
    assert "players.registration_status =" in sql
    assert params["registration_status_1"] == RegistrationStatus.PENDING


def test_player_repo_update_rating_data_updates_requested_fields(run_async):
    session = RecordingSession()
    repo = PlayerRepository(session)

    run_async(repo.update_rating_data(7, current_rating=88.5, division_rank=2))

    assert session.commits == 1
    params = _params(session.executed[0])
    assert params["id_1"] == 7
    assert params["current_rating"] == 88.5
    assert params["division_rank"] == 2


def test_transfer_repo_get_active_for_player_uses_active_statuses(run_async):
    session = RecordingSession(result=None)
    repo = TransferRepository(session)

    run_async(repo.get_active_for_player(9))

    params = _params(session.executed[0])
    assert params["player_id_1"] == 9
    statuses = params["status_1"]
    assert statuses == [
        TransferStatus.PENDING_CAPTAIN,
        TransferStatus.PENDING_PLAYER_CONFIRM,
        TransferStatus.PENDING_CAPTAIN_CONFIRM,
        TransferStatus.PENDING_ADMIN,
    ]


def test_transfer_repo_get_pending_for_captain_builds_exit_query(run_async):
    session = RecordingSession(result=[])
    repo = TransferRepository(session)

    result = run_async(repo.get_pending_for_captain(11, TransferType.EXIT))

    assert result == []
    params = _params(session.executed[0])
    assert params["from_club_id_1"] == 11
    assert params["transfer_type_1"] == TransferType.EXIT
    assert params["status_1"] == TransferStatus.PENDING_CAPTAIN


def test_transfer_repo_get_pending_for_captain_builds_invite_confirm_query(run_async):
    session = RecordingSession(result=[])
    repo = TransferRepository(session)

    run_async(repo.get_pending_for_captain(12, TransferType.INVITE))

    params = _params(session.executed[0])
    assert params["to_club_id_1"] == 12
    assert params["transfer_type_1"] == TransferType.INVITE
    assert params["status_1"] == TransferStatus.PENDING_CAPTAIN_CONFIRM


def test_transfer_repo_get_pending_for_captain_returns_empty_for_unknown_type(run_async):
    session = RecordingSession(result=[])
    repo = TransferRepository(session)

    result = run_async(repo.get_pending_for_captain(13, "unknown"))

    assert result == []
    assert session.executed == []


def test_transfer_repo_get_free_agents_filters_role_status_and_activity(run_async):
    session = RecordingSession(result=[])
    repo = TransferRepository(session)

    run_async(repo.get_free_agents())

    params = _params(session.executed[0])
    assert params["role_1"] == "free_agent"
    assert params["registration_status_1"] == RegistrationStatus.APPROVED


def test_transfer_repo_update_status_writes_rejected_by_when_present(run_async):
    session = RecordingSession()
    repo = TransferRepository(session)

    run_async(repo.update_status(17, TransferStatus.REJECTED, rejected_by="captain"))

    assert session.commits == 1
    params = _params(session.executed[0])
    assert params["id_1"] == 17
    assert params["status"] == TransferStatus.REJECTED
    assert params["rejected_by"] == "captain"


def test_club_repo_get_by_tournament_id_orders_by_name(run_async):
    session = RecordingSession(result=[])
    repo = ClubRepository(session)

    result = run_async(repo.get_by_tournament_id(22))

    assert result == []
    sql = _sql(session.executed[0])
    params = _params(session.executed[0])
    assert "clubs.tournament_id =" in sql
    assert "ORDER BY clubs.name" in sql
    assert params["tournament_id_1"] == 22


def test_club_repo_update_name_updates_and_commits(run_async):
    session = RecordingSession()
    repo = ClubRepository(session)

    run_async(repo.update_name(5, "Новый клуб"))

    assert session.commits == 1
    params = _params(session.executed[0])
    assert params["id_1"] == 5
    assert params["name"] == "Новый клуб"


def test_club_repo_upsert_from_scrape_creates_when_missing(run_async):
    session = RecordingSession(result=None)
    repo = ClubRepository(session)

    club = run_async(repo.upsert_from_scrape("Элит", tournament_id=7, external_id="ext-1"))

    assert club.name == "Элит"
    assert club.tournament_id == 7
    assert club.external_id == "ext-1"
    assert session.added == [club]
    assert session.refreshed == [club]
    assert session.commits == 1


def test_tournament_repo_get_all_orders_by_name(run_async):
    session = RecordingSession(result=[])
    repo = TournamentRepository(session)

    result = run_async(repo.get_all())

    assert result == []
    sql = _sql(session.executed[0])
    assert "ORDER BY tournaments.name" in sql


def test_tournament_repo_get_by_id_uses_session_get(run_async):
    stub = object()
    session = RecordingSession(result=stub)
    repo = TournamentRepository(session)

    result = run_async(repo.get_by_id(9))

    assert result is stub
    assert len(session.get_calls) == 1
    assert session.get_calls[0][1] == 9


def test_tournament_repo_upsert_creates_when_missing(run_async):
    session = RecordingSession(result=None)
    repo = TournamentRepository(session)

    tournament = run_async(repo.upsert("Высший", external_id="tour-1"))

    assert tournament.name == "Высший"
    assert tournament.external_id == "tour-1"
    assert session.added == [tournament]
    assert session.refreshed == [tournament]
    assert session.commits == 1
