from football_bot.handlers.user import transfer_handlers
from football_bot.keyboards.inline.registration_kb import ClubCallback
from football_bot.keyboards.inline.transfer_kb import (
    KickPlayerCallback,
    TransferDecisionCallback,
    TransferPlayerCallback,
)
from football_bot.locales import messages as msg
from football_bot.models import PlayerRole, TransferRequest, TransferStatus, TransferType
from football_bot.states import FSMTransfer


def _make_request(
    *,
    request_id: int,
    player,
    transfer_type: TransferType,
    status: TransferStatus,
    from_club_id=None,
    to_club_id=None,
    initiated_by=None,
    from_club=None,
    to_club=None,
):
    request = TransferRequest(
        id=request_id,
        player_id=player.id,
        transfer_type=transfer_type,
        status=status,
        from_club_id=from_club_id,
        to_club_id=to_club_id,
        initiated_by=initiated_by or player.telegram_id,
    )
    request.player = player
    if from_club is not None:
        request.from_club = from_club
    if to_club is not None:
        request.to_club = to_club
    return request


def test_player_exit_club_notifies_captain_on_success(
    monkeypatch, run_async, callback_factory, player_factory
):
    player = player_factory(player_id=1, telegram_id=501, role=PlayerRole.PLAYER, club_id=10)
    captain = player_factory(player_id=2, telegram_id=601, role=PlayerRole.CAPTAIN, club_id=10)
    request = _make_request(
        request_id=11,
        player=player,
        transfer_type=TransferType.EXIT,
        status=TransferStatus.PENDING_CAPTAIN,
        from_club_id=10,
    )

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

        async def get_captain_of_club(self, club_id):
            assert club_id == 10
            return captain

        async def create_exit_request(self, requested_player):
            assert requested_player is player
            return request

    monkeypatch.setattr(transfer_handlers, "PlayerRepository", FakePlayerRepo)
    monkeypatch.setattr(transfer_handlers, "TransferService", FakeTransferService)
    callback = callback_factory(user_id=501)

    run_async(transfer_handlers.player_exit_club(callback, session=object()))

    assert callback.message.answers == [{"text": msg.TRANSFER_EXIT_SENT, "reply_markup": None}]
    assert callback.bot.sent_messages == [
        {
            "chat_id": 601,
            "text": msg.TRANSFER_EXIT_CAPTAIN_NOTIF.format(name="Ivan Petrov"),
            "reply_markup": callback.bot.sent_messages[0]["reply_markup"],
        }
    ]
    assert callback.bot.sent_messages[0]["reply_markup"] is not None


def test_transfer_choose_club_notifies_target_captain_on_success(
    monkeypatch, run_async, callback_factory, state_factory, player_factory
):
    player = player_factory(player_id=3, telegram_id=502, role=PlayerRole.FREE_AGENT, club_id=None)
    captain = player_factory(player_id=4, telegram_id=602, role=PlayerRole.CAPTAIN, club_id=22)
    club = type("ClubStub", (), {"name": "Элит"})()
    request = _make_request(
        request_id=12,
        player=player,
        transfer_type=TransferType.JOIN,
        status=TransferStatus.PENDING_CAPTAIN,
        to_club_id=22,
    )

    class FakePlayerRepo:
        def __init__(self, _session):
            pass

        async def get_by_telegram_id(self, _telegram_id):
            return player

    class FakeTransferService:
        def __init__(self, _session):
            pass

        async def get_captain_of_club(self, club_id):
            assert club_id == 22
            return captain

        async def create_join_request(self, requested_player, to_club_id):
            assert requested_player is player
            assert to_club_id == 22
            return request

    class FakeClubRepo:
        def __init__(self, _session):
            pass

        async def get_by_id(self, club_id):
            assert club_id == 22
            return club

    monkeypatch.setattr(transfer_handlers, "PlayerRepository", FakePlayerRepo)
    monkeypatch.setattr(transfer_handlers, "TransferService", FakeTransferService)
    monkeypatch.setattr(transfer_handlers, "ClubRepository", FakeClubRepo)
    callback = callback_factory(user_id=502)
    state = state_factory({"tournament_id": 7})

    run_async(
        transfer_handlers.transfer_choose_club(
            callback,
            ClubCallback(club_id=22),
            state,
            session=object(),
        )
    )

    assert state.cleared is True
    assert callback.message.answers == [
        {"text": msg.TRANSFER_JOIN_SENT.format(club="Элит"), "reply_markup": None}
    ]
    assert callback.bot.sent_messages[0]["chat_id"] == 602
    assert callback.bot.sent_messages[0]["text"] == msg.TRANSFER_JOIN_CAPTAIN_NOTIF.format(
        name="Ivan Petrov"
    )
    assert callback.bot.sent_messages[0]["reply_markup"] is not None


def test_captain_invite_fa_notifies_free_agent_on_success(
    monkeypatch, run_async, callback_factory, player_factory
):
    captain = player_factory(player_id=5, telegram_id=503, role=PlayerRole.CAPTAIN, club_id=30)
    target = player_factory(player_id=6, telegram_id=603, role=PlayerRole.FREE_AGENT, club_id=None)
    club = type("ClubStub", (), {"name": "РЖД"})()
    request = _make_request(
        request_id=13,
        player=target,
        transfer_type=TransferType.INVITE,
        status=TransferStatus.PENDING_PLAYER_CONFIRM,
        to_club_id=30,
        initiated_by=503,
    )

    class FakePlayerRepo:
        def __init__(self, _session):
            pass

        async def get_by_telegram_id(self, _telegram_id):
            return captain

        async def get_by_id(self, player_id):
            assert player_id == 6
            return target

    class FakeTransferService:
        def __init__(self, _session):
            pass

        async def get_active_for_player(self, _player_id):
            return None

        async def create_invite(self, requesting_captain, player_id, club_id):
            assert requesting_captain is captain
            assert player_id == 6
            assert club_id == 30
            return request

    class FakeClubRepo:
        def __init__(self, _session):
            pass

        async def get_by_id(self, club_id):
            assert club_id == 30
            return club

    monkeypatch.setattr(transfer_handlers, "PlayerRepository", FakePlayerRepo)
    monkeypatch.setattr(transfer_handlers, "TransferService", FakeTransferService)
    monkeypatch.setattr(transfer_handlers, "ClubRepository", FakeClubRepo)
    callback = callback_factory(user_id=503)

    run_async(
        transfer_handlers.captain_invite_fa(
            callback,
            TransferPlayerCallback(player_id=6),
            session=object(),
        )
    )

    assert callback.message.answers == [
        {"text": msg.TRANSFER_INVITE_SENT.format(name="Ivan Petrov"), "reply_markup": None}
    ]
    assert callback.bot.sent_messages[0]["chat_id"] == 603
    assert callback.bot.sent_messages[0]["text"] == msg.TRANSFER_INVITE_PLAYER_NOTIF.format(
        club="РЖД"
    )
    assert callback.bot.sent_messages[0]["reply_markup"] is not None


def test_captain_kick_player_notifies_all_admins_on_success(
    monkeypatch, run_async, callback_factory, player_factory
):
    captain = player_factory(player_id=7, telegram_id=504, role=PlayerRole.CAPTAIN, club_id=40)
    target = player_factory(player_id=8, telegram_id=604, role=PlayerRole.PLAYER, club_id=40)
    club = type("ClubStub", (), {"name": "Оптик"})()
    request = _make_request(
        request_id=14,
        player=target,
        transfer_type=TransferType.KICK,
        status=TransferStatus.PENDING_ADMIN,
        from_club_id=40,
        initiated_by=504,
    )

    class FakePlayerRepo:
        def __init__(self, _session):
            pass

        async def get_by_telegram_id(self, _telegram_id):
            return captain

        async def get_by_id(self, player_id):
            assert player_id == 8
            return target

    class FakeTransferService:
        def __init__(self, _session):
            pass

        async def create_kick_request(self, requesting_captain, player_id):
            assert requesting_captain is captain
            assert player_id == 8
            return request

    class FakeClubRepo:
        def __init__(self, _session):
            pass

        async def get_by_id(self, club_id):
            assert club_id == 40
            return club

    monkeypatch.setattr(transfer_handlers, "PlayerRepository", FakePlayerRepo)
    monkeypatch.setattr(transfer_handlers, "TransferService", FakeTransferService)
    monkeypatch.setattr(transfer_handlers, "ClubRepository", FakeClubRepo)
    callback = callback_factory(user_id=504)

    run_async(
        transfer_handlers.captain_kick_player(
            callback,
            KickPlayerCallback(player_id=8),
            session=object(),
            admin_ids=[1],
            league_admin_ids=[2, 1],
        )
    )

    assert callback.message.edited_text == [
        {
            "text": msg.TRANSFER_KICK_SENT_ADMIN.format(name="Ivan Petrov"),
            "reply_markup": None,
        }
    ]
    assert {item["chat_id"] for item in callback.bot.sent_messages} == {1, 2}
    assert {
        item["text"] for item in callback.bot.sent_messages
    } == {
        msg.TRANSFER_KICK_ADMIN_NOTIF.format(name="Ivan Petrov", club="Оптик")
    }
    assert all(item["reply_markup"] is not None for item in callback.bot.sent_messages)


def test_decision_approve_exit_notifies_player_and_admins(
    monkeypatch, run_async, callback_factory, player_factory
):
    actor = player_factory(player_id=9, telegram_id=505, role=PlayerRole.CAPTAIN, club_id=50)
    player = player_factory(player_id=10, telegram_id=605, role=PlayerRole.PLAYER, club_id=50)
    request = _make_request(
        request_id=15,
        player=player,
        transfer_type=TransferType.EXIT,
        status=TransferStatus.PENDING_ADMIN,
        from_club_id=50,
    )
    club = type("ClubStub", (), {"name": "Элит"})()

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

        async def captain_approve(self, _request_id):
            return request

    class FakeClubRepo:
        def __init__(self, _session):
            pass

        async def get_by_id(self, club_id):
            assert club_id == 50
            return club

    monkeypatch.setattr(transfer_handlers, "PlayerRepository", FakePlayerRepo)
    monkeypatch.setattr(transfer_handlers, "TransferService", FakeTransferService)
    monkeypatch.setattr(transfer_handlers, "ClubRepository", FakeClubRepo)
    callback = callback_factory(user_id=505)

    run_async(
        transfer_handlers.decision_approve(
            callback,
            TransferDecisionCallback(request_id=15, action="approve"),
            session=object(),
            admin_ids=[1],
            league_admin_ids=[2],
        )
    )

    assert callback.message.edited_text == [
        {"text": "✅ Вы одобрили выход Ivan Petrov", "reply_markup": None}
    ]
    assert callback.bot.sent_messages[0]["chat_id"] == 605
    assert callback.bot.sent_messages[0]["text"] == msg.TRANSFER_EXIT_CAPTAIN_APPROVED
    admin_messages = callback.bot.sent_messages[1:]
    assert {item["chat_id"] for item in admin_messages} == {1, 2}
    assert {
        item["text"] for item in admin_messages
    } == {
        msg.TRANSFER_EXIT_ADMIN_NOTIF.format(name="Ivan Petrov", club="Элит")
    }


def test_decision_approve_join_notifies_player_only(
    monkeypatch, run_async, callback_factory, player_factory
):
    actor = player_factory(player_id=11, telegram_id=506, role=PlayerRole.CAPTAIN, club_id=60)
    player = player_factory(player_id=12, telegram_id=606, role=PlayerRole.PLAYER, club_id=10)
    request = _make_request(
        request_id=16,
        player=player,
        transfer_type=TransferType.JOIN,
        status=TransferStatus.PENDING_PLAYER_CONFIRM,
        to_club_id=60,
    )
    club = type("ClubStub", (), {"name": "РЖД"})()

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

        async def captain_approve(self, _request_id):
            return request

    class FakeClubRepo:
        def __init__(self, _session):
            pass

        async def get_by_id(self, club_id):
            assert club_id == 60
            return club

    monkeypatch.setattr(transfer_handlers, "PlayerRepository", FakePlayerRepo)
    monkeypatch.setattr(transfer_handlers, "TransferService", FakeTransferService)
    monkeypatch.setattr(transfer_handlers, "ClubRepository", FakeClubRepo)
    callback = callback_factory(user_id=506)

    run_async(
        transfer_handlers.decision_approve(
            callback,
            TransferDecisionCallback(request_id=16, action="approve"),
            session=object(),
            admin_ids=[1],
            league_admin_ids=[2],
        )
    )

    assert callback.message.edited_text == [
        {"text": "✅ Вы одобрили трансфер Ivan Petrov", "reply_markup": None}
    ]
    assert len(callback.bot.sent_messages) == 1
    assert callback.bot.sent_messages[0]["chat_id"] == 606
    assert callback.bot.sent_messages[0]["text"] == msg.TRANSFER_JOIN_CAPTAIN_APPROVED.format(
        club="РЖД"
    )
    assert callback.bot.sent_messages[0]["reply_markup"] is not None


def test_decision_approve_invite_by_free_agent_notifies_captain(
    monkeypatch, run_async, callback_factory, player_factory
):
    actor = player_factory(player_id=13, telegram_id=607, role=PlayerRole.FREE_AGENT, club_id=None)
    captain = player_factory(player_id=14, telegram_id=507, role=PlayerRole.CAPTAIN, club_id=70)
    to_club = type("ClubStub", (), {"name": "РЖД"})()
    request = _make_request(
        request_id=17,
        player=actor,
        transfer_type=TransferType.INVITE,
        status=TransferStatus.PENDING_CAPTAIN_CONFIRM,
        to_club_id=70,
        to_club=to_club,
    )

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

        async def player_accept_invite(self, _request_id):
            return request

        async def get_captain_of_club(self, club_id):
            assert club_id == 70
            return captain

    monkeypatch.setattr(transfer_handlers, "PlayerRepository", FakePlayerRepo)
    monkeypatch.setattr(transfer_handlers, "TransferService", FakeTransferService)
    callback = callback_factory(user_id=607)

    run_async(
        transfer_handlers.decision_approve(
            callback,
            TransferDecisionCallback(request_id=17, action="approve"),
            session=object(),
            admin_ids=[],
            league_admin_ids=[],
        )
    )

    assert callback.message.edited_text == [
        {"text": "✅ Вы приняли приглашение от клуба РЖД", "reply_markup": None}
    ]
    assert callback.bot.sent_messages[0]["chat_id"] == 507
    assert callback.bot.sent_messages[0]["text"] == msg.TRANSFER_INVITE_PLAYER_ACCEPTED_CAPTAIN.format(
        name="Ivan Petrov"
    )
    assert callback.bot.sent_messages[0]["reply_markup"] is not None


def test_decision_reject_exit_notifies_player(
    monkeypatch, run_async, callback_factory, player_factory
):
    actor = player_factory(player_id=15, telegram_id=508, role=PlayerRole.CAPTAIN, club_id=80)
    player = player_factory(player_id=16, telegram_id=608, role=PlayerRole.PLAYER, club_id=80)
    request = _make_request(
        request_id=18,
        player=player,
        transfer_type=TransferType.EXIT,
        status=TransferStatus.REJECTED,
        from_club_id=80,
    )

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

        async def captain_reject(self, _request_id):
            return request

    monkeypatch.setattr(transfer_handlers, "PlayerRepository", FakePlayerRepo)
    monkeypatch.setattr(transfer_handlers, "TransferService", FakeTransferService)
    callback = callback_factory(user_id=508)

    run_async(
        transfer_handlers.decision_reject(
            callback,
            TransferDecisionCallback(request_id=18, action="reject"),
            session=object(),
        )
    )

    assert callback.message.edited_text == [
        {"text": "❌ Вы отклонили заявку Ivan Petrov", "reply_markup": None}
    ]
    assert callback.bot.sent_messages == [
        {
            "chat_id": 608,
            "text": msg.TRANSFER_EXIT_CAPTAIN_REJECTED,
            "reply_markup": None,
        }
    ]


def test_decision_reject_invite_by_free_agent_notifies_captain(
    monkeypatch, run_async, callback_factory, player_factory
):
    actor = player_factory(player_id=17, telegram_id=609, role=PlayerRole.FREE_AGENT, club_id=None)
    captain = player_factory(player_id=18, telegram_id=509, role=PlayerRole.CAPTAIN, club_id=90)
    request = _make_request(
        request_id=19,
        player=actor,
        transfer_type=TransferType.INVITE,
        status=TransferStatus.REJECTED,
        to_club_id=90,
    )

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

        async def player_reject_invite(self, _request_id):
            return request

        async def get_captain_of_club(self, club_id):
            assert club_id == 90
            return captain

    monkeypatch.setattr(transfer_handlers, "PlayerRepository", FakePlayerRepo)
    monkeypatch.setattr(transfer_handlers, "TransferService", FakeTransferService)
    callback = callback_factory(user_id=609)

    run_async(
        transfer_handlers.decision_reject(
            callback,
            TransferDecisionCallback(request_id=19, action="reject"),
            session=object(),
        )
    )

    assert callback.message.edited_text == [
        {"text": "❌ Вы отклонили приглашение", "reply_markup": None}
    ]
    assert callback.bot.sent_messages == [
        {
            "chat_id": 509,
            "text": msg.TRANSFER_INVITE_PLAYER_REJECTED.format(name="Ivan Petrov"),
            "reply_markup": None,
        }
    ]


def test_decision_confirm_join_notifies_admins(
    monkeypatch, run_async, callback_factory, player_factory
):
    actor = player_factory(player_id=19, telegram_id=610, role=PlayerRole.PLAYER, club_id=20)
    to_club = type("ClubStub", (), {"name": "Элит"})()
    request = _make_request(
        request_id=20,
        player=actor,
        transfer_type=TransferType.JOIN,
        status=TransferStatus.PENDING_ADMIN,
        to_club_id=20,
        to_club=to_club,
    )
    club = type("ClubStub", (), {"name": "Элит"})()

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

        async def player_confirm_join(self, _request_id):
            return request

    class FakeClubRepo:
        def __init__(self, _session):
            pass

        async def get_by_id(self, club_id):
            assert club_id == 20
            return club

    monkeypatch.setattr(transfer_handlers, "PlayerRepository", FakePlayerRepo)
    monkeypatch.setattr(transfer_handlers, "TransferService", FakeTransferService)
    monkeypatch.setattr(transfer_handlers, "ClubRepository", FakeClubRepo)
    callback = callback_factory(user_id=610)

    run_async(
        transfer_handlers.decision_confirm(
            callback,
            TransferDecisionCallback(request_id=20, action="confirm"),
            session=object(),
            admin_ids=[1],
            league_admin_ids=[2],
        )
    )

    assert callback.message.edited_text == [
        {"text": "✅ Вы подтвердили переход в клуб Элит", "reply_markup": None}
    ]
    assert {item["chat_id"] for item in callback.bot.sent_messages} == {1, 2}
    assert {
        item["text"] for item in callback.bot.sent_messages
    } == {
        msg.TRANSFER_JOIN_PLAYER_CONFIRMED_ADMIN.format(name="Ivan Petrov", club="Элит")
    }


def test_decision_confirm_invite_by_captain_notifies_player_and_admins(
    monkeypatch, run_async, callback_factory, player_factory
):
    actor = player_factory(player_id=20, telegram_id=511, role=PlayerRole.CAPTAIN, club_id=21)
    player = player_factory(player_id=21, telegram_id=611, role=PlayerRole.FREE_AGENT, club_id=None)
    to_club = type("ClubStub", (), {"name": "РЖД"})()
    request = _make_request(
        request_id=21,
        player=player,
        transfer_type=TransferType.INVITE,
        status=TransferStatus.PENDING_ADMIN,
        to_club_id=21,
        to_club=to_club,
        initiated_by=511,
    )
    club = type("ClubStub", (), {"name": "РЖД"})()

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

        async def captain_confirm_invite(self, _request_id):
            return request

    class FakeClubRepo:
        def __init__(self, _session):
            pass

        async def get_by_id(self, club_id):
            assert club_id == 21
            return club

    monkeypatch.setattr(transfer_handlers, "PlayerRepository", FakePlayerRepo)
    monkeypatch.setattr(transfer_handlers, "TransferService", FakeTransferService)
    monkeypatch.setattr(transfer_handlers, "ClubRepository", FakeClubRepo)
    callback = callback_factory(user_id=511)

    run_async(
        transfer_handlers.decision_confirm(
            callback,
            TransferDecisionCallback(request_id=21, action="confirm"),
            session=object(),
            admin_ids=[1],
            league_admin_ids=[2],
        )
    )

    assert callback.message.edited_text == [
        {"text": "✅ Вы подтвердили вступление Ivan Petrov", "reply_markup": None}
    ]
    assert callback.bot.sent_messages[0]["chat_id"] == 611
    assert callback.bot.sent_messages[0]["text"] == msg.TRANSFER_INVITE_CAPTAIN_CONFIRMED_PLAYER.format(
        club="РЖД"
    )
    admin_messages = callback.bot.sent_messages[1:]
    assert {item["chat_id"] for item in admin_messages} == {1, 2}
    assert {
        item["text"] for item in admin_messages
    } == {
        msg.TRANSFER_INVITE_CAPTAIN_CONFIRMED_ADMIN.format(name="Ivan Petrov", club="РЖД")
    }
