from sqlalchemy.dialects import postgresql

from football_bot.models import (
    PlayerRole,
    TransferRequest,
    TransferStatus,
    TransferType,
)
from football_bot.service.transfer_service import TransferService


class RecordingSession:
    def __init__(self):
        self.executed = []
        self.commits = 0

    async def execute(self, stmt):
        self.executed.append(stmt)

    async def commit(self):
        self.commits += 1


def _compiled_params(stmt):
    return stmt.compile(dialect=postgresql.dialect()).params


def test_create_join_request_uses_expected_fields(monkeypatch, run_async, player_factory):
    player = player_factory(player_id=10, telegram_id=555, club_id=3)

    class FakeTransferRepo:
        created_request = None

        def __init__(self, _session):
            pass

        async def create(self, request):
            self.created_request = request
            request.id = 77
            return request

    class FakePlayerRepo:
        def __init__(self, _session):
            pass

    monkeypatch.setattr("football_bot.service.transfer_service.TransferRepository", FakeTransferRepo)
    monkeypatch.setattr("football_bot.service.transfer_service.PlayerRepository", FakePlayerRepo)
    svc = TransferService(session=RecordingSession())

    request = run_async(svc.create_join_request(player, to_club_id=9))

    assert request.id == 77
    assert request.player_id == 10
    assert request.transfer_type == TransferType.JOIN
    assert request.status == TransferStatus.PENDING_CAPTAIN
    assert request.from_club_id == 3
    assert request.to_club_id == 9
    assert request.initiated_by == 555


def test_captain_approve_changes_status_for_exit_and_join(monkeypatch, run_async):
    class FakeTransferRepo:
        request = None
        status_updates = []

        def __init__(self, _session):
            pass

        async def get_by_id(self, _request_id):
            return self.request

        async def update_status(self, request_id, status, rejected_by=None):
            self.status_updates.append((request_id, status, rejected_by))
            self.request.status = status

    class FakePlayerRepo:
        def __init__(self, _session):
            pass

    monkeypatch.setattr("football_bot.service.transfer_service.TransferRepository", FakeTransferRepo)
    monkeypatch.setattr("football_bot.service.transfer_service.PlayerRepository", FakePlayerRepo)

    for transfer_type, expected_status in (
        (TransferType.EXIT, TransferStatus.PENDING_ADMIN),
        (TransferType.JOIN, TransferStatus.PENDING_PLAYER_CONFIRM),
    ):
        FakeTransferRepo.status_updates = []
        FakeTransferRepo.request = TransferRequest(
            id=15,
            player_id=1,
            transfer_type=transfer_type,
            status=TransferStatus.PENDING_CAPTAIN,
            from_club_id=10,
            to_club_id=20,
            initiated_by=100,
        )
        svc = TransferService(session=RecordingSession())

        result = run_async(svc.captain_approve(15))

        assert result.status == expected_status
        assert FakeTransferRepo.status_updates == [(15, expected_status, None)]


def test_admin_approve_exit_and_kick_make_player_free_agent(monkeypatch, run_async):
    class FakeTransferRepo:
        request = None
        status_updates = []

        def __init__(self, _session):
            pass

        async def get_by_id(self, _request_id):
            return self.request

        async def update_status(self, request_id, status, rejected_by=None):
            self.status_updates.append((request_id, status, rejected_by))
            self.request.status = status

    class FakePlayerRepo:
        def __init__(self, _session):
            pass

    monkeypatch.setattr("football_bot.service.transfer_service.TransferRepository", FakeTransferRepo)
    monkeypatch.setattr("football_bot.service.transfer_service.PlayerRepository", FakePlayerRepo)

    for transfer_type in (TransferType.EXIT, TransferType.KICK):
        session = RecordingSession()
        FakeTransferRepo.status_updates = []
        FakeTransferRepo.request = TransferRequest(
            id=21,
            player_id=7,
            transfer_type=transfer_type,
            status=TransferStatus.PENDING_ADMIN,
            from_club_id=11,
            to_club_id=None,
            initiated_by=100,
        )
        svc = TransferService(session=session)

        result = run_async(svc.admin_approve(21))

        assert result.status == TransferStatus.APPROVED
        assert FakeTransferRepo.status_updates == [(21, TransferStatus.APPROVED, None)]
        assert session.commits == 1
        assert len(session.executed) == 1
        params = _compiled_params(session.executed[0])
        assert params["id_1"] == 7
        assert params["club_id"] is None
        assert params["role"] == PlayerRole.FREE_AGENT


def test_admin_approve_join_and_invite_assign_player_to_target_club(monkeypatch, run_async):
    class FakeTransferRepo:
        request = None
        status_updates = []

        def __init__(self, _session):
            pass

        async def get_by_id(self, _request_id):
            return self.request

        async def update_status(self, request_id, status, rejected_by=None):
            self.status_updates.append((request_id, status, rejected_by))
            self.request.status = status

    class FakePlayerRepo:
        def __init__(self, _session):
            pass

    monkeypatch.setattr("football_bot.service.transfer_service.TransferRepository", FakeTransferRepo)
    monkeypatch.setattr("football_bot.service.transfer_service.PlayerRepository", FakePlayerRepo)

    for transfer_type in (TransferType.JOIN, TransferType.INVITE):
        session = RecordingSession()
        FakeTransferRepo.status_updates = []
        FakeTransferRepo.request = TransferRequest(
            id=22,
            player_id=8,
            transfer_type=transfer_type,
            status=TransferStatus.PENDING_ADMIN,
            from_club_id=None,
            to_club_id=33,
            initiated_by=100,
        )
        svc = TransferService(session=session)

        result = run_async(svc.admin_approve(22))

        assert result.status == TransferStatus.APPROVED
        assert FakeTransferRepo.status_updates == [(22, TransferStatus.APPROVED, None)]
        assert session.commits == 1
        assert len(session.executed) == 1
        params = _compiled_params(session.executed[0])
        assert params["id_1"] == 8
        assert params["club_id"] == 33
        assert params["role"] == PlayerRole.PLAYER
