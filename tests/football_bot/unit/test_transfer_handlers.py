from football_bot.handlers.user import transfer_handlers
from football_bot.keyboards.inline.registration_kb import ClubCallback
from football_bot.keyboards.inline.transfer_kb import (
    TransferDecisionCallback,
    TransferPlayerCallback,
)
from football_bot.locales import messages as msg
from football_bot.models import PlayerRole, TransferRequest, TransferStatus, TransferType
from football_bot.states import FSMTransfer


def test_player_exit_club_requires_membership(monkeypatch, run_async, callback_factory, player_factory):
    player = player_factory(telegram_id=50, club_id=None)

    class FakePlayerRepo:
        def __init__(self, _session):
            pass

        async def get_by_telegram_id(self, _telegram_id):
            return player

    monkeypatch.setattr(transfer_handlers, "PlayerRepository", FakePlayerRepo)
    callback = callback_factory(user_id=50)

    run_async(transfer_handlers.player_exit_club(callback, session=object()))

    assert callback.answers == [{"text": msg.TRANSFER_NO_CLUB, "show_alert": True}]
    assert callback.message.answers == []


def test_start_join_flow_blocks_when_active_request_exists(monkeypatch, run_async, callback_factory, state_factory, player_factory):
    player = player_factory(telegram_id=51, role=PlayerRole.FREE_AGENT, club_id=None)

    class FakePlayerRepo:
        def __init__(self, _session):
            pass

        async def get_by_telegram_id(self, _telegram_id):
            return player

    class FakeTransferService:
        def __init__(self, _session):
            pass

        async def get_active_for_player(self, _player_id):
            return object()

    monkeypatch.setattr(transfer_handlers, "PlayerRepository", FakePlayerRepo)
    monkeypatch.setattr(transfer_handlers, "TransferService", FakeTransferService)
    callback = callback_factory(user_id=51)
    state = state_factory()

    run_async(transfer_handlers.start_join_flow(callback, state, session=object()))

    assert callback.answers == [{"text": msg.TRANSFER_ACTIVE_EXISTS, "show_alert": True}]
    assert callback.message.answers == []
    assert state.current_state is None


def test_transfer_choose_club_rejects_same_club(monkeypatch, run_async, callback_factory, state_factory, player_factory):
    player = player_factory(telegram_id=52, club_id=15)

    class FakePlayerRepo:
        def __init__(self, _session):
            pass

        async def get_by_telegram_id(self, _telegram_id):
            return player

    monkeypatch.setattr(transfer_handlers, "PlayerRepository", FakePlayerRepo)
    callback = callback_factory(user_id=52)
    state = state_factory({"tournament_id": 3})

    run_async(
        transfer_handlers.transfer_choose_club(
            callback,
            ClubCallback(club_id=15),
            state,
            session=object(),
        )
    )

    assert state.cleared is True
    assert callback.answers == [{"text": msg.TRANSFER_SAME_CLUB, "show_alert": True}]
    assert callback.message.answers == []


def test_captain_invite_fa_rejects_non_free_agent_targets(monkeypatch, run_async, callback_factory, player_factory):
    captain = player_factory(
        player_id=10,
        telegram_id=60,
        role=PlayerRole.CAPTAIN,
        club_id=8,
    )
    target = player_factory(
        player_id=20,
        telegram_id=61,
        role=PlayerRole.PLAYER,
        club_id=None,
    )

    class FakePlayerRepo:
        def __init__(self, _session):
            pass

        async def get_by_telegram_id(self, _telegram_id):
            return captain

        async def get_by_id(self, player_id):
            assert player_id == 20
            return target

    class FakeTransferService:
        def __init__(self, _session):
            pass

    monkeypatch.setattr(transfer_handlers, "PlayerRepository", FakePlayerRepo)
    monkeypatch.setattr(transfer_handlers, "TransferService", FakeTransferService)
    callback = callback_factory(user_id=60)

    run_async(
        transfer_handlers.captain_invite_fa(
            callback,
            TransferPlayerCallback(player_id=20),
            session=object(),
        )
    )

    assert callback.answers == [{"text": msg.TRANSFER_ACTION_FORBIDDEN, "show_alert": True}]
    assert callback.message.answers == []


def test_decision_approve_forbids_unrelated_captain(monkeypatch, run_async, callback_factory, player_factory):
    actor = player_factory(
        player_id=30,
        telegram_id=70,
        role=PlayerRole.CAPTAIN,
        club_id=99,
    )
    target = player_factory(player_id=40, telegram_id=71)
    request = TransferRequest(
        id=91,
        player_id=40,
        transfer_type=TransferType.JOIN,
        status=TransferStatus.PENDING_CAPTAIN,
        from_club_id=None,
        to_club_id=10,
        initiated_by=71,
    )
    request.player = target

    class FakePlayerRepo:
        def __init__(self, _session):
            pass

        async def get_by_telegram_id(self, _telegram_id):
            return actor

    class FakeTransferService:
        def __init__(self, _session):
            pass

        async def get_request(self, _request_id):
            return request

    monkeypatch.setattr(transfer_handlers, "PlayerRepository", FakePlayerRepo)
    monkeypatch.setattr(transfer_handlers, "TransferService", FakeTransferService)
    callback = callback_factory(user_id=70)

    run_async(
        transfer_handlers.decision_approve(
            callback,
            TransferDecisionCallback(request_id=91, action="approve"),
            session=object(),
            admin_ids=[],
            league_admin_ids=[],
        )
    )

    assert callback.answers == [{"text": msg.TRANSFER_ACTION_FORBIDDEN, "show_alert": True}]
    assert callback.message.edited_text == []


def test_start_join_flow_sets_tournament_state_when_tournaments_exist(
    monkeypatch, run_async, callback_factory, state_factory, player_factory
):
    player = player_factory(telegram_id=72, role=PlayerRole.FREE_AGENT, club_id=None)
    tournaments = [type("TournamentStub", (), {"id": 1, "name": "Высший"})()]

    class FakePlayerRepo:
        def __init__(self, _session):
            pass

        async def get_by_telegram_id(self, _telegram_id):
            return player

    class FakeTransferService:
        def __init__(self, _session):
            pass

        async def get_active_for_player(self, _player_id):
            return None

    class FakeTournamentRepo:
        def __init__(self, _session):
            pass

        async def get_all(self):
            return tournaments

    monkeypatch.setattr(transfer_handlers, "PlayerRepository", FakePlayerRepo)
    monkeypatch.setattr(transfer_handlers, "TransferService", FakeTransferService)
    monkeypatch.setattr(transfer_handlers, "TournamentRepository", FakeTournamentRepo)
    callback = callback_factory(user_id=72)
    state = state_factory()

    run_async(transfer_handlers.start_join_flow(callback, state, session=object()))

    assert state.current_state == FSMTransfer.choose_tournament
    assert callback.message.answers[0]["text"] == msg.REG_CHOOSE_TOURNAMENT
    assert callback.answers[-1] == {"text": None, "show_alert": False}
