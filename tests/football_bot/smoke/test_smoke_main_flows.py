from types import SimpleNamespace

from football_bot.handlers.admin import admin_panel_handlers, transfer_admin_handlers
from football_bot.handlers.user import registration_handlers, transfer_handlers
from football_bot.keyboards.inline.admin_panel_kb import AdminClubCallback, AdminPanelAction, AdminPlayerCallback
from football_bot.keyboards.inline.registration_kb import ClubCallback, PositionCallback, TournamentCallback
from football_bot.keyboards.inline.transfer_kb import AdminTransferAction, TransferDecisionCallback, TransferPlayerCallback
from football_bot.locales import messages as msg
from football_bot.models import PlayerRole, TransferRequest, TransferStatus, TransferType
from football_bot.states import FSMAdminEditClub, FSMAdminEditRating, FSMRegistration, FSMTransfer


ACTIVE_STATUSES = {
    TransferStatus.PENDING_CAPTAIN,
    TransferStatus.PENDING_PLAYER_CONFIRM,
    TransferStatus.PENDING_CAPTAIN_CONFIRM,
    TransferStatus.PENDING_ADMIN,
}


def _club_stub(club_id: int, name: str, tournament=None):
    return type("ClubStub", (), {"id": club_id, "name": name, "tournament": tournament})()


def _tournament_stub(tournament_id: int, name: str):
    return type("TournamentStub", (), {"id": tournament_id, "name": name})()


def _make_callback_with_bot(callback_factory, bot, *, user_id, data=None):
    callback = callback_factory(user_id=user_id, data=data)
    callback.bot = bot
    return callback


class SmokeTransferHarness:
    def __init__(self, monkeypatch, callback_factory, players, clubs, tournaments):
        self.players_by_id = {player.id: player for player in players}
        self.players_by_tg = {player.telegram_id: player for player in players}
        self.clubs = clubs
        self.tournaments = tournaments
        self.requests = {}
        self.next_request_id = 100
        self.shared_bot = callback_factory().bot

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

            async def get_by_tournament_id(self, tournament_id):
                return [
                    club for club in harness.clubs.values()
                    if getattr(club.tournament, "id", None) == tournament_id
                ]

        class FlowTournamentRepo:
            def __init__(self, _session):
                pass

            async def get_all(self):
                return list(harness.tournaments.values())

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

            async def get_free_agents(self):
                return [
                    player for player in harness.players_by_id.values()
                    if player.role == PlayerRole.FREE_AGENT
                ]

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
                if request.transfer_type == TransferType.EXIT:
                    player.club_id = None
                    player.role = PlayerRole.FREE_AGENT
                else:
                    player.club_id = request.to_club_id
                    player.role = PlayerRole.PLAYER
                return request

        monkeypatch.setattr(transfer_handlers, "PlayerRepository", FlowPlayerRepo)
        monkeypatch.setattr(transfer_handlers, "ClubRepository", FlowClubRepo)
        monkeypatch.setattr(transfer_handlers, "TournamentRepository", FlowTournamentRepo)
        monkeypatch.setattr(transfer_handlers, "TransferService", FlowTransferService)
        monkeypatch.setattr(transfer_admin_handlers, "TransferService", FlowTransferService)

    def create_request(
        self,
        *,
        player,
        transfer_type,
        status,
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
        if from_club_id is not None:
            request.from_club = self.clubs[from_club_id]
        if to_club_id is not None:
            request.to_club = self.clubs[to_club_id]
        self.requests[request.id] = request
        return request


def test_smoke_registration_free_agent_flow(
    monkeypatch, run_async, callback_factory, message_factory, state_factory, player_factory
):
    created_player = player_factory(
        player_id=201,
        telegram_id=7001,
        role=PlayerRole.FREE_AGENT,
        club_id=None,
    )

    class FakeRegistrationService:
        create_calls = []

        def __init__(self, _session):
            pass

        async def get_player(self, _telegram_id):
            return None

        async def create_registration(self, **kwargs):
            self.create_calls.append(kwargs)
            return created_player

    monkeypatch.setattr(registration_handlers, "RegistrationService", FakeRegistrationService)

    state = state_factory()
    start_cb = callback_factory(user_id=7001)
    run_async(registration_handlers.start_registration(start_cb, state, session=object()))
    assert state.current_state == FSMRegistration.enter_first_name

    run_async(registration_handlers.process_first_name(message_factory(text="Ivan", user_id=7001), state))
    run_async(registration_handlers.process_last_name(message_factory(text="Petrov", user_id=7001), state))

    position_cb = callback_factory(user_id=7001)
    run_async(
        registration_handlers.process_position(
            position_cb,
            PositionCallback(position="defender"),
            state,
        )
    )

    run_async(registration_handlers.process_description(message_factory(text="Stable defender", user_id=7001), state))
    run_async(registration_handlers.process_birth_date(message_factory(text="01.02.2000", user_id=7001), state))
    run_async(
        registration_handlers.process_photo(
            message_factory(photo=[SimpleNamespace(file_id="p1"), SimpleNamespace(file_id="p2")], user_id=7001),
            state,
        )
    )

    final_cb = callback_factory(user_id=7001, username="free_agent_smoke")
    run_async(
        registration_handlers.status_free_agent(
            final_cb,
            state,
            session=object(),
            admin_ids=[9001],
            league_admin_ids=[9002],
        )
    )

    assert FakeRegistrationService.create_calls[0]["first_name"] == "Ivan"
    assert FakeRegistrationService.create_calls[0]["last_name"] == "Petrov"
    assert FakeRegistrationService.create_calls[0]["photo_file_id"] == "p2"
    assert FakeRegistrationService.create_calls[0]["role"] == PlayerRole.FREE_AGENT
    assert final_cb.message.answers == [{"text": msg.NOTIF_REG_SENT, "reply_markup": None}]
    assert [item["chat_id"] for item in final_cb.bot.sent_photos] == [9001, 9002]
    assert state.cleared is True


def test_smoke_registration_club_player_flow(
    monkeypatch, run_async, callback_factory, message_factory, state_factory, player_factory
):
    created_player = player_factory(
        player_id=202,
        telegram_id=7002,
        role=PlayerRole.PLAYER,
        club_id=81,
    )
    tournament = _tournament_stub(31, "Суперлига")
    club = _club_stub(81, "Элит", tournament=tournament)

    class FakeRegistrationService:
        create_calls = []

        def __init__(self, _session):
            pass

        async def get_player(self, _telegram_id):
            return None

        async def create_registration(self, **kwargs):
            self.create_calls.append(kwargs)
            return created_player

    class FakeTournamentRepo:
        def __init__(self, _session):
            pass

        async def get_all(self):
            return [tournament]

    class FakeClubRepo:
        def __init__(self, _session):
            pass

        async def get_by_tournament_id(self, tournament_id):
            assert tournament_id == 31
            return [club]

        async def get_by_id(self, club_id):
            assert club_id == 81
            return club

    monkeypatch.setattr(registration_handlers, "RegistrationService", FakeRegistrationService)
    monkeypatch.setattr(registration_handlers, "TournamentRepository", FakeTournamentRepo)
    monkeypatch.setattr(registration_handlers, "ClubRepository", FakeClubRepo)

    state = state_factory()
    run_async(registration_handlers.start_registration(callback_factory(user_id=7002), state, session=object()))
    run_async(registration_handlers.process_first_name(message_factory(text="Pavel", user_id=7002), state))
    run_async(registration_handlers.process_last_name(message_factory(text="Sidorov", user_id=7002), state))
    run_async(
        registration_handlers.process_position(
            callback_factory(user_id=7002),
            PositionCallback(position="forward"),
            state,
        )
    )
    run_async(registration_handlers.skip_description(callback_factory(user_id=7002, data="skip"), state))
    run_async(registration_handlers.process_birth_date(message_factory(text="05.05.2001", user_id=7002), state))
    run_async(
        registration_handlers.process_photo(
            message_factory(photo=[SimpleNamespace(file_id="club-photo")], user_id=7002),
            state,
        )
    )
    run_async(registration_handlers.status_choose_club(callback_factory(user_id=7002), state, session=object()))
    assert state.current_state == FSMRegistration.choose_tournament
    run_async(
        registration_handlers.process_tournament(
            callback_factory(user_id=7002),
            TournamentCallback(tournament_id=31),
            state,
            session=object(),
        )
    )
    assert state.current_state == FSMRegistration.choose_club
    run_async(
        registration_handlers.process_club(
            callback_factory(user_id=7002),
            ClubCallback(club_id=81),
            state,
        )
    )
    assert state.current_state == FSMRegistration.choose_role

    final_cb = callback_factory(user_id=7002, username="club_smoke", data="role_player")
    run_async(
        registration_handlers.process_role(
            final_cb,
            state,
            session=object(),
            admin_ids=[9001],
            league_admin_ids=[9002],
        )
    )

    assert FakeRegistrationService.create_calls[0]["first_name"] == "Pavel"
    assert FakeRegistrationService.create_calls[0]["club_id"] == 81
    assert FakeRegistrationService.create_calls[0]["role"] == PlayerRole.PLAYER
    assert final_cb.message.answers == [{"text": msg.NOTIF_REG_SENT, "reply_markup": None}]
    assert [item["chat_id"] for item in final_cb.bot.sent_photos] == [9001, 9002]
    assert state.cleared is True


def test_smoke_transfer_exit_flow(monkeypatch, run_async, callback_factory, player_factory):
    player = player_factory(player_id=301, telegram_id=7101, role=PlayerRole.PLAYER, club_id=10)
    captain = player_factory(player_id=302, telegram_id=7102, role=PlayerRole.CAPTAIN, club_id=10)
    harness = SmokeTransferHarness(
        monkeypatch,
        callback_factory,
        [player, captain],
        {10: _club_stub(10, "Элит")},
        {},
    )

    player_cb = _make_callback_with_bot(callback_factory, harness.shared_bot, user_id=7101)
    run_async(transfer_handlers.player_exit_club(player_cb, session=object()))
    request_id = next(iter(harness.requests))

    captain_cb = _make_callback_with_bot(callback_factory, harness.shared_bot, user_id=7102)
    run_async(
        transfer_handlers.decision_approve(
            captain_cb,
            TransferDecisionCallback(request_id=request_id, action="approve"),
            session=object(),
            admin_ids=[9001],
            league_admin_ids=[9002],
        )
    )

    admin_cb = _make_callback_with_bot(callback_factory, harness.shared_bot, user_id=9001)
    run_async(
        transfer_admin_handlers.admin_approve_transfer(
            admin_cb,
            AdminTransferAction(action="approve", request_id=request_id),
            session=object(),
        )
    )

    assert player.role == PlayerRole.FREE_AGENT
    assert player.club_id is None
    texts = [item["text"] for item in harness.shared_bot.sent_messages]
    assert msg.TRANSFER_EXIT_CAPTAIN_APPROVED in texts
    assert msg.TRANSFER_EXIT_ADMIN_APPROVED in texts


def test_smoke_transfer_join_flow(monkeypatch, run_async, callback_factory, state_factory, player_factory):
    tournament = _tournament_stub(51, "Суперлига")
    player = player_factory(player_id=303, telegram_id=7201, role=PlayerRole.FREE_AGENT, club_id=None)
    captain = player_factory(player_id=304, telegram_id=7202, role=PlayerRole.CAPTAIN, club_id=20)
    harness = SmokeTransferHarness(
        monkeypatch,
        callback_factory,
        [player, captain],
        {20: _club_stub(20, "РЖД", tournament=tournament)},
        {51: tournament},
    )

    start_cb = _make_callback_with_bot(callback_factory, harness.shared_bot, user_id=7201)
    state = state_factory()
    run_async(transfer_handlers.start_join_flow(start_cb, state, session=object()))
    assert state.current_state == FSMTransfer.choose_tournament

    tourn_cb = _make_callback_with_bot(callback_factory, harness.shared_bot, user_id=7201)
    run_async(
        transfer_handlers.transfer_choose_tournament(
            tourn_cb,
            TournamentCallback(tournament_id=51),
            state,
            session=object(),
        )
    )
    assert state.current_state == FSMTransfer.choose_club

    club_cb = _make_callback_with_bot(callback_factory, harness.shared_bot, user_id=7201)
    run_async(
        transfer_handlers.transfer_choose_club(
            club_cb,
            ClubCallback(club_id=20),
            state,
            session=object(),
        )
    )
    request_id = next(iter(harness.requests))

    captain_cb = _make_callback_with_bot(callback_factory, harness.shared_bot, user_id=7202)
    run_async(
        transfer_handlers.decision_approve(
            captain_cb,
            TransferDecisionCallback(request_id=request_id, action="approve"),
            session=object(),
            admin_ids=[9001],
            league_admin_ids=[9002],
        )
    )

    player_confirm_cb = _make_callback_with_bot(callback_factory, harness.shared_bot, user_id=7201)
    run_async(
        transfer_handlers.decision_confirm(
            player_confirm_cb,
            TransferDecisionCallback(request_id=request_id, action="confirm"),
            session=object(),
            admin_ids=[9001],
            league_admin_ids=[9002],
        )
    )

    admin_cb = _make_callback_with_bot(callback_factory, harness.shared_bot, user_id=9001)
    run_async(
        transfer_admin_handlers.admin_approve_transfer(
            admin_cb,
            AdminTransferAction(action="approve", request_id=request_id),
            session=object(),
        )
    )

    assert player.role == PlayerRole.PLAYER
    assert player.club_id == 20
    texts = [item["text"] for item in harness.shared_bot.sent_messages]
    assert msg.TRANSFER_JOIN_CAPTAIN_APPROVED.format(club="РЖД") in texts
    assert msg.TRANSFER_JOIN_ADMIN_APPROVED.format(club="РЖД") in texts


def test_smoke_transfer_captain_invite_flow(monkeypatch, run_async, callback_factory, player_factory):
    tournament = _tournament_stub(61, "Суперлига")
    captain = player_factory(player_id=305, telegram_id=7301, role=PlayerRole.CAPTAIN, club_id=30)
    free_agent = player_factory(player_id=306, telegram_id=7302, role=PlayerRole.FREE_AGENT, club_id=None)
    harness = SmokeTransferHarness(
        monkeypatch,
        callback_factory,
        [captain, free_agent],
        {30: _club_stub(30, "Оптик", tournament=tournament)},
        {61: tournament},
    )

    list_cb = _make_callback_with_bot(callback_factory, harness.shared_bot, user_id=7301)
    run_async(transfer_handlers.captain_view_free_agents(list_cb, session=object()))
    assert list_cb.message.answers

    invite_cb = _make_callback_with_bot(callback_factory, harness.shared_bot, user_id=7301)
    run_async(
        transfer_handlers.captain_invite_fa(
            invite_cb,
            TransferPlayerCallback(player_id=306),
            session=object(),
        )
    )
    request_id = next(iter(harness.requests))

    fa_accept_cb = _make_callback_with_bot(callback_factory, harness.shared_bot, user_id=7302)
    run_async(
        transfer_handlers.decision_approve(
            fa_accept_cb,
            TransferDecisionCallback(request_id=request_id, action="approve"),
            session=object(),
            admin_ids=[],
            league_admin_ids=[],
        )
    )

    captain_confirm_cb = _make_callback_with_bot(callback_factory, harness.shared_bot, user_id=7301)
    run_async(
        transfer_handlers.decision_confirm(
            captain_confirm_cb,
            TransferDecisionCallback(request_id=request_id, action="confirm"),
            session=object(),
            admin_ids=[9001],
            league_admin_ids=[9002],
        )
    )

    admin_cb = _make_callback_with_bot(callback_factory, harness.shared_bot, user_id=9001)
    run_async(
        transfer_admin_handlers.admin_approve_transfer(
            admin_cb,
            AdminTransferAction(action="approve", request_id=request_id),
            session=object(),
        )
    )

    assert free_agent.role == PlayerRole.PLAYER
    assert free_agent.club_id == 30
    texts = [item["text"] for item in harness.shared_bot.sent_messages]
    assert msg.TRANSFER_INVITE_PLAYER_ACCEPTED_CAPTAIN.format(name="Ivan Petrov") in texts
    assert msg.TRANSFER_INVITE_ADMIN_APPROVED.format(club="Оптик") in texts


def test_smoke_admin_panel_club_and_rating_flows(
    monkeypatch, run_async, callback_factory, message_factory, state_factory, player_factory
):
    club = _club_stub(91, "Старое имя")
    player = player_factory(player_id=401, first_name="Roman", last_name="Romanov")

    class FakeClubRepo:
        updates = []

        def __init__(self, _session):
            pass

        async def get_all(self):
            return [club]

        async def get_by_id(self, club_id):
            assert club_id == 91
            return club

        async def update_name(self, club_id, new_name):
            self.updates.append((club_id, new_name))

    class FakePlayerRepo:
        update_calls = []

        def __init__(self, _session):
            pass

        async def get_all_approved(self):
            return [player]

        async def get_by_id(self, player_id):
            assert player_id == 401
            return player

        async def update_rating_data(self, player_id, **kwargs):
            self.update_calls.append((player_id, kwargs))

    monkeypatch.setattr(admin_panel_handlers, "ClubRepository", FakeClubRepo)
    monkeypatch.setattr(admin_panel_handlers, "PlayerRepository", FakePlayerRepo)

    panel_message = message_factory(text="/admin", user_id=9001)
    run_async(admin_panel_handlers.admin_panel(panel_message))
    assert panel_message.answers[0]["text"] == msg.ADMIN_PANEL_HEADER

    club_state = state_factory()
    club_start_cb = callback_factory(user_id=9001)
    run_async(admin_panel_handlers.admin_edit_club_start(club_start_cb, session=object(), state=club_state))
    assert club_state.current_state == FSMAdminEditClub.choose_club

    club_choose_cb = callback_factory(user_id=9001)
    run_async(
        admin_panel_handlers.admin_edit_club_chosen(
            club_choose_cb,
            AdminClubCallback(club_id=91),
            club_state,
            session=object(),
        )
    )
    assert club_state.current_state == FSMAdminEditClub.enter_new_name

    run_async(
        admin_panel_handlers.admin_edit_club_name(
            message_factory(text="Новое имя", user_id=9001),
            club_state,
            session=object(),
        )
    )
    assert FakeClubRepo.updates == [(91, "Новое имя")]

    current_rating_state = state_factory()
    current_rating_start_cb = callback_factory(user_id=9001)
    run_async(
        admin_panel_handlers.admin_edit_rating_start(
            current_rating_start_cb,
            AdminPanelAction(action="edit_rating"),
            session=object(),
            state=current_rating_state,
        )
    )
    assert current_rating_state.current_state == FSMAdminEditRating.choose_player
    current_rating_choose_cb = callback_factory(user_id=9001)
    run_async(
        admin_panel_handlers.admin_edit_rating_chosen(
            current_rating_choose_cb,
            AdminPlayerCallback(player_id=401),
            current_rating_state,
            session=object(),
        )
    )
    assert current_rating_state.current_state == FSMAdminEditRating.enter_rating
    run_async(
        admin_panel_handlers.admin_edit_rating_value(
            message_factory(text="88.4", user_id=9001),
            current_rating_state,
            session=object(),
        )
    )

    prev_rating_state = state_factory()
    prev_rating_start_cb = callback_factory(user_id=9001)
    run_async(
        admin_panel_handlers.admin_edit_rating_start(
            prev_rating_start_cb,
            AdminPanelAction(action="edit_prev_rating"),
            session=object(),
            state=prev_rating_state,
        )
    )
    prev_rating_choose_cb = callback_factory(user_id=9001)
    run_async(
        admin_panel_handlers.admin_edit_rating_chosen(
            prev_rating_choose_cb,
            AdminPlayerCallback(player_id=401),
            prev_rating_state,
            session=object(),
        )
    )
    run_async(
        admin_panel_handlers.admin_edit_rating_value(
            message_factory(text="77.7", user_id=9001),
            prev_rating_state,
            session=object(),
        )
    )

    assert FakePlayerRepo.update_calls[0][0] == 401
    assert FakePlayerRepo.update_calls[0][1]["current_rating"] == 88.4
    assert FakePlayerRepo.update_calls[1][0] == 401
    assert FakePlayerRepo.update_calls[1][1]["prev_season_rating"] == 77.7

    async def fake_build(_session):
        return "players.csv", b"id,current_rating\n1,10\n", 1

    monkeypatch.setattr(admin_panel_handlers, "_build_scraped_players_export", fake_build)
    export_cb = callback_factory(user_id=9001)
    run_async(admin_panel_handlers.admin_export_all_players(export_cb, session=object()))
    assert export_cb.message.documents[0]["document"].filename == "players.csv"
