from football_bot.handlers.admin import transfer_admin_handlers
from football_bot.handlers.user import transfer_handlers
from football_bot.keyboards.inline.registration_kb import ClubCallback
from football_bot.keyboards.inline.transfer_kb import (
    AdminTransferAction,
    KickPlayerCallback,
    TransferDecisionCallback,
    TransferPlayerCallback,
)
from football_bot.locales import messages as msg
from football_bot.models import PlayerRole, TransferRequest, TransferStatus, TransferType


ACTIVE_STATUSES = {
    TransferStatus.PENDING_CAPTAIN,
    TransferStatus.PENDING_PLAYER_CONFIRM,
    TransferStatus.PENDING_CAPTAIN_CONFIRM,
    TransferStatus.PENDING_ADMIN,
}


def _club_stub(club_id: int, name: str):
    return type("ClubStub", (), {"id": club_id, "name": name, "tournament": None})()


def _make_callback_with_bot(callback_factory, bot, *, user_id, data=None):
    callback = callback_factory(user_id=user_id, data=data)
    callback.bot = bot
    return callback


class FlowHarness:
    def __init__(self, monkeypatch, player_factory, players, clubs):
        self.players_by_id = {player.id: player for player in players}
        self.players_by_tg = {player.telegram_id: player for player in players}
        self.clubs = clubs
        self.requests = {}
        self.next_request_id = 100

        harness = self

        class FlowPlayerRepo:
            def __init__(self, _session):
                pass

            async def get_by_telegram_id(self, telegram_id):
                return harness.players_by_tg.get(telegram_id)

            async def get_by_id(self, player_id):
                return harness.players_by_id.get(player_id)

        class FlowClubRepo:
            def __init__(self, _session):
                pass

            async def get_by_id(self, club_id):
                return harness.clubs.get(club_id)

        class FlowTransferService:
            def __init__(self, _session):
                pass

            async def get_active_for_player(self, player_id):
                for request in harness.requests.values():
                    if request.player_id == player_id and request.status in ACTIVE_STATUSES:
                        return request
                return None

            async def get_request(self, request_id):
                return harness.requests.get(request_id)

            async def get_captain_of_club(self, club_id):
                for player in harness.players_by_id.values():
                    if player.club_id == club_id and player.role == PlayerRole.CAPTAIN:
                        return player
                return None

            async def get_player_by_telegram_id(self, telegram_id):
                return harness.players_by_tg.get(telegram_id)

            async def create_exit_request(self, player):
                return harness.create_request(
                    player=player,
                    transfer_type=TransferType.EXIT,
                    status=TransferStatus.PENDING_CAPTAIN,
                    from_club_id=player.club_id,
                    initiated_by=player.telegram_id,
                )

            async def create_join_request(self, player, to_club_id):
                return harness.create_request(
                    player=player,
                    transfer_type=TransferType.JOIN,
                    status=TransferStatus.PENDING_CAPTAIN,
                    from_club_id=player.club_id,
                    to_club_id=to_club_id,
                    initiated_by=player.telegram_id,
                )

            async def create_invite(self, captain, player_id, club_id):
                return harness.create_request(
                    player=harness.players_by_id[player_id],
                    transfer_type=TransferType.INVITE,
                    status=TransferStatus.PENDING_PLAYER_CONFIRM,
                    to_club_id=club_id,
                    initiated_by=captain.telegram_id,
                )

            async def create_kick_request(self, captain, target_player_id):
                return harness.create_request(
                    player=harness.players_by_id[target_player_id],
                    transfer_type=TransferType.KICK,
                    status=TransferStatus.PENDING_ADMIN,
                    from_club_id=captain.club_id,
                    initiated_by=captain.telegram_id,
                )

            async def captain_approve(self, request_id):
                request = harness.requests[request_id]
                if request.transfer_type == TransferType.EXIT:
                    request.status = TransferStatus.PENDING_ADMIN
                elif request.transfer_type == TransferType.JOIN:
                    request.status = TransferStatus.PENDING_PLAYER_CONFIRM
                return request

            async def player_confirm_join(self, request_id):
                request = harness.requests[request_id]
                request.status = TransferStatus.PENDING_ADMIN
                return request

            async def player_accept_invite(self, request_id):
                request = harness.requests[request_id]
                request.status = TransferStatus.PENDING_CAPTAIN_CONFIRM
                return request

            async def captain_confirm_invite(self, request_id):
                request = harness.requests[request_id]
                request.status = TransferStatus.PENDING_ADMIN
                return request

            async def admin_approve(self, request_id):
                request = harness.requests[request_id]
                request.status = TransferStatus.APPROVED
                player = harness.players_by_id[request.player_id]

                if request.transfer_type in (TransferType.EXIT, TransferType.KICK):
                    player.club_id = None
                    player.role = PlayerRole.FREE_AGENT
                else:
                    player.club_id = request.to_club_id
                    player.role = PlayerRole.PLAYER

                return request

        monkeypatch.setattr(transfer_handlers, "PlayerRepository", FlowPlayerRepo)
        monkeypatch.setattr(transfer_handlers, "ClubRepository", FlowClubRepo)
        monkeypatch.setattr(transfer_handlers, "TransferService", FlowTransferService)
        monkeypatch.setattr(transfer_admin_handlers, "TransferService", FlowTransferService)

    def create_request(
        self,
        *,
        player,
        transfer_type: TransferType,
        status: TransferStatus,
        from_club_id=None,
        to_club_id=None,
        initiated_by=None,
    ):
        request = TransferRequest(
            id=self.next_request_id,
            player_id=player.id,
            transfer_type=transfer_type,
            status=status,
            from_club_id=from_club_id,
            to_club_id=to_club_id,
            initiated_by=initiated_by or player.telegram_id,
        )
        self.next_request_id += 1
        request.player = player
        if from_club_id is not None and from_club_id in self.clubs:
            request.from_club = self.clubs[from_club_id]
        if to_club_id is not None and to_club_id in self.clubs:
            request.to_club = self.clubs[to_club_id]
        self.requests[request.id] = request
        return request


def test_end_to_end_player_exit_flow(monkeypatch, run_async, callback_factory, player_factory):
    player = player_factory(player_id=1, telegram_id=1001, role=PlayerRole.PLAYER, club_id=10)
    captain = player_factory(player_id=2, telegram_id=1002, role=PlayerRole.CAPTAIN, club_id=10)
    harness = FlowHarness(
        monkeypatch,
        player_factory,
        [player, captain],
        {10: _club_stub(10, "Элит")},
    )

    shared_bot = _make_callback_with_bot(callback_factory, callback_factory().bot, user_id=0).bot

    player_cb = _make_callback_with_bot(callback_factory, shared_bot, user_id=1001)
    run_async(transfer_handlers.player_exit_club(player_cb, session=object()))
    request_id = next(iter(harness.requests))

    captain_cb = _make_callback_with_bot(callback_factory, shared_bot, user_id=1002)
    run_async(
        transfer_handlers.decision_approve(
            captain_cb,
            TransferDecisionCallback(request_id=request_id, action="approve"),
            session=object(),
            admin_ids=[9001],
            league_admin_ids=[9002],
        )
    )

    admin_cb = _make_callback_with_bot(callback_factory, shared_bot, user_id=9001)
    run_async(
        transfer_admin_handlers.admin_approve_transfer(
            admin_cb,
            AdminTransferAction(action="approve", request_id=request_id),
            session=object(),
        )
    )

    assert player.role == PlayerRole.FREE_AGENT
    assert player.club_id is None
    assert [item["chat_id"] for item in shared_bot.sent_messages] == [
        1002, 1001, 9001, 9002, 1001, 1002,
    ]
    assert shared_bot.sent_messages[0]["text"] == msg.TRANSFER_EXIT_CAPTAIN_NOTIF.format(
        name="Ivan Petrov"
    )
    assert shared_bot.sent_messages[1]["text"] == msg.TRANSFER_EXIT_CAPTAIN_APPROVED
    assert shared_bot.sent_messages[2]["text"] == msg.TRANSFER_EXIT_ADMIN_NOTIF.format(
        name="Ivan Petrov", club="Элит"
    )
    assert shared_bot.sent_messages[4]["text"] == msg.TRANSFER_EXIT_ADMIN_APPROVED
    assert shared_bot.sent_messages[5]["text"] == msg.TRANSFER_EXIT_ADMIN_APPROVED_CAPTAIN.format(
        name="Ivan Petrov"
    )


def test_end_to_end_player_join_flow(monkeypatch, run_async, callback_factory, state_factory, player_factory):
    player = player_factory(player_id=3, telegram_id=1101, role=PlayerRole.FREE_AGENT, club_id=None)
    captain = player_factory(player_id=4, telegram_id=1102, role=PlayerRole.CAPTAIN, club_id=20)
    harness = FlowHarness(
        monkeypatch,
        player_factory,
        [player, captain],
        {20: _club_stub(20, "РЖД")},
    )

    shared_bot = _make_callback_with_bot(callback_factory, callback_factory().bot, user_id=0).bot

    join_cb = _make_callback_with_bot(callback_factory, shared_bot, user_id=1101)
    run_async(
        transfer_handlers.transfer_choose_club(
            join_cb,
            ClubCallback(club_id=20),
            state_factory({"tournament_id": 1}),
            session=object(),
        )
    )
    request_id = next(iter(harness.requests))

    captain_cb = _make_callback_with_bot(callback_factory, shared_bot, user_id=1102)
    run_async(
        transfer_handlers.decision_approve(
            captain_cb,
            TransferDecisionCallback(request_id=request_id, action="approve"),
            session=object(),
            admin_ids=[9001],
            league_admin_ids=[9002],
        )
    )

    player_confirm_cb = _make_callback_with_bot(callback_factory, shared_bot, user_id=1101)
    run_async(
        transfer_handlers.decision_confirm(
            player_confirm_cb,
            TransferDecisionCallback(request_id=request_id, action="confirm"),
            session=object(),
            admin_ids=[9001],
            league_admin_ids=[9002],
        )
    )

    admin_cb = _make_callback_with_bot(callback_factory, shared_bot, user_id=9001)
    run_async(
        transfer_admin_handlers.admin_approve_transfer(
            admin_cb,
            AdminTransferAction(action="approve", request_id=request_id),
            session=object(),
        )
    )

    assert player.role == PlayerRole.PLAYER
    assert player.club_id == 20
    assert [item["chat_id"] for item in shared_bot.sent_messages] == [
        1102, 1101, 9001, 9002, 1101, 1102,
    ]
    assert shared_bot.sent_messages[0]["text"] == msg.TRANSFER_JOIN_CAPTAIN_NOTIF.format(
        name="Ivan Petrov"
    )
    assert shared_bot.sent_messages[1]["text"] == msg.TRANSFER_JOIN_CAPTAIN_APPROVED.format(
        club="РЖД"
    )
    assert shared_bot.sent_messages[2]["text"] == msg.TRANSFER_JOIN_PLAYER_CONFIRMED_ADMIN.format(
        name="Ivan Petrov", club="РЖД"
    )
    assert shared_bot.sent_messages[4]["text"] == msg.TRANSFER_JOIN_ADMIN_APPROVED.format(
        club="РЖД"
    )
    assert shared_bot.sent_messages[5]["text"] == msg.TRANSFER_JOIN_ADMIN_APPROVED_CAPTAIN.format(
        name="Ivan Petrov"
    )


def test_end_to_end_captain_invite_flow(monkeypatch, run_async, callback_factory, player_factory):
    captain = player_factory(player_id=5, telegram_id=1201, role=PlayerRole.CAPTAIN, club_id=30)
    free_agent = player_factory(player_id=6, telegram_id=1202, role=PlayerRole.FREE_AGENT, club_id=None)
    harness = FlowHarness(
        monkeypatch,
        player_factory,
        [captain, free_agent],
        {30: _club_stub(30, "Оптик")},
    )

    shared_bot = _make_callback_with_bot(callback_factory, callback_factory().bot, user_id=0).bot

    captain_invite_cb = _make_callback_with_bot(callback_factory, shared_bot, user_id=1201)
    run_async(
        transfer_handlers.captain_invite_fa(
            captain_invite_cb,
            TransferPlayerCallback(player_id=6),
            session=object(),
        )
    )
    request_id = next(iter(harness.requests))

    fa_accept_cb = _make_callback_with_bot(callback_factory, shared_bot, user_id=1202)
    run_async(
        transfer_handlers.decision_approve(
            fa_accept_cb,
            TransferDecisionCallback(request_id=request_id, action="approve"),
            session=object(),
            admin_ids=[],
            league_admin_ids=[],
        )
    )

    captain_confirm_cb = _make_callback_with_bot(callback_factory, shared_bot, user_id=1201)
    run_async(
        transfer_handlers.decision_confirm(
            captain_confirm_cb,
            TransferDecisionCallback(request_id=request_id, action="confirm"),
            session=object(),
            admin_ids=[9001],
            league_admin_ids=[9002],
        )
    )

    admin_cb = _make_callback_with_bot(callback_factory, shared_bot, user_id=9001)
    run_async(
        transfer_admin_handlers.admin_approve_transfer(
            admin_cb,
            AdminTransferAction(action="approve", request_id=request_id),
            session=object(),
        )
    )

    assert free_agent.role == PlayerRole.PLAYER
    assert free_agent.club_id == 30
    assert [item["chat_id"] for item in shared_bot.sent_messages] == [
        1202, 1201, 1202, 9001, 9002, 1202, 1201,
    ]
    assert shared_bot.sent_messages[0]["text"] == msg.TRANSFER_INVITE_PLAYER_NOTIF.format(
        club="Оптик"
    )
    assert shared_bot.sent_messages[1]["text"] == msg.TRANSFER_INVITE_PLAYER_ACCEPTED_CAPTAIN.format(
        name="Ivan Petrov"
    )
    assert shared_bot.sent_messages[2]["text"] == msg.TRANSFER_INVITE_CAPTAIN_CONFIRMED_PLAYER.format(
        club="Оптик"
    )
    assert shared_bot.sent_messages[3]["text"] == msg.TRANSFER_INVITE_CAPTAIN_CONFIRMED_ADMIN.format(
        name="Ivan Petrov", club="Оптик"
    )
    assert shared_bot.sent_messages[5]["text"] == msg.TRANSFER_INVITE_ADMIN_APPROVED.format(
        club="Оптик"
    )
    assert shared_bot.sent_messages[6]["text"] == msg.TRANSFER_INVITE_ADMIN_APPROVED_CAPTAIN.format(
        name="Ivan Petrov"
    )


def test_end_to_end_captain_kick_flow(monkeypatch, run_async, callback_factory, player_factory):
    captain = player_factory(player_id=7, telegram_id=1301, role=PlayerRole.CAPTAIN, club_id=40)
    player = player_factory(player_id=8, telegram_id=1302, role=PlayerRole.PLAYER, club_id=40)
    FlowHarness(
        monkeypatch,
        player_factory,
        [captain, player],
        {40: _club_stub(40, "Первый клуб")},
    )

    shared_bot = _make_callback_with_bot(callback_factory, callback_factory().bot, user_id=0).bot

    kick_cb = _make_callback_with_bot(callback_factory, shared_bot, user_id=1301)
    run_async(
        transfer_handlers.captain_kick_player(
            kick_cb,
            KickPlayerCallback(player_id=8),
            session=object(),
            admin_ids=[9001],
            league_admin_ids=[9002],
        )
    )

    request_id = 100
    admin_cb = _make_callback_with_bot(callback_factory, shared_bot, user_id=9001)
    run_async(
        transfer_admin_handlers.admin_approve_transfer(
            admin_cb,
            AdminTransferAction(action="approve", request_id=request_id),
            session=object(),
        )
    )

    assert player.role == PlayerRole.FREE_AGENT
    assert player.club_id is None
    assert [item["chat_id"] for item in shared_bot.sent_messages] == [9001, 9002, 1302, 1301]
    assert shared_bot.sent_messages[0]["text"] == msg.TRANSFER_KICK_ADMIN_NOTIF.format(
        name="Ivan Petrov", club="Первый клуб"
    )
    assert shared_bot.sent_messages[2]["text"] == msg.TRANSFER_KICK_ADMIN_APPROVED.format(
        club="Первый клуб"
    )
    assert shared_bot.sent_messages[3]["text"] == msg.TRANSFER_KICK_ADMIN_APPROVED_CAPTAIN.format(
        name="Ivan Petrov"
    )
