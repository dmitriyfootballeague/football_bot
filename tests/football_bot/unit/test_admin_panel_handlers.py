from datetime import datetime, timezone

from football_bot.models import Club, ScrapedPlayerStats, Tournament
from football_bot.handlers.admin import admin_panel_handlers
from football_bot.keyboards.inline.admin_panel_kb import (
    AdminClubCallback,
    AdminPanelAction,
    AdminPlayerCallback,
)
from football_bot.locales import messages as msg
from football_bot.states import FSMAdminEditClub, FSMAdminEditRating


def _button_callback_data(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]


def test_admin_panel_shows_header(run_async, message_factory):
    message = message_factory(text="/admin")

    run_async(admin_panel_handlers.admin_panel(message))

    assert message.answers[0]["text"] == msg.ADMIN_PANEL_HEADER
    assert message.answers[0]["reply_markup"] is not None


def test_admin_edit_club_start_handles_empty_list(monkeypatch, run_async, callback_factory, state_factory):
    class FakeClubRepo:
        def __init__(self, _session):
            pass

        async def get_all(self):
            return []

    monkeypatch.setattr(admin_panel_handlers, "ClubRepository", FakeClubRepo)
    callback = callback_factory(user_id=1001)
    state = state_factory()

    run_async(admin_panel_handlers.admin_edit_club_start(callback, session=object(), state=state))

    assert callback.message.answers == [{"text": msg.ADMIN_NO_CLUBS, "reply_markup": None}]
    assert state.current_state is None


def test_admin_edit_club_start_sets_choose_state(monkeypatch, run_async, callback_factory, state_factory):
    clubs = [type("ClubStub", (), {"id": 1, "name": "Элит"})()]

    class FakeClubRepo:
        def __init__(self, _session):
            pass

        async def get_all(self):
            return clubs

    monkeypatch.setattr(admin_panel_handlers, "ClubRepository", FakeClubRepo)
    callback = callback_factory(user_id=1002)
    state = state_factory()

    run_async(admin_panel_handlers.admin_edit_club_start(callback, session=object(), state=state))

    assert callback.message.answers[0]["text"] == msg.ADMIN_CHOOSE_CLUB
    assert callback.message.answers[0]["reply_markup"] is not None
    assert _button_callback_data(callback.message.answers[0]["reply_markup"])[-1] == (
        AdminPanelAction(action="cancel").pack()
    )
    assert state.current_state == FSMAdminEditClub.choose_club


def test_admin_edit_club_chosen_missing_club(monkeypatch, run_async, callback_factory, state_factory):
    class FakeClubRepo:
        def __init__(self, _session):
            pass

        async def get_by_id(self, _club_id):
            return None

    monkeypatch.setattr(admin_panel_handlers, "ClubRepository", FakeClubRepo)
    callback = callback_factory(user_id=1003)
    state = state_factory()

    run_async(
        admin_panel_handlers.admin_edit_club_chosen(
            callback,
            AdminClubCallback(club_id=5),
            state,
            session=object(),
        )
    )

    assert callback.answers == [{"text": "Клуб не найден", "show_alert": True}]
    assert state.data == {}


def test_admin_edit_club_name_validates_blank_input(run_async, message_factory, state_factory):
    message = message_factory(text="   ")
    state = state_factory({"club_id": 7})

    run_async(admin_panel_handlers.admin_edit_club_name(message, state, session=object()))

    assert message.answers[0]["text"] == msg.ADMIN_ENTER_CLUB_NAME
    assert message.answers[0]["reply_markup"] is not None
    assert _button_callback_data(message.answers[0]["reply_markup"]) == [
        AdminPanelAction(action="cancel").pack()
    ]
    assert state.cleared is False


def test_admin_edit_club_name_updates_name(monkeypatch, run_async, message_factory, state_factory):
    class FakeClubRepo:
        updates = []

        def __init__(self, _session):
            pass

        async def update_name(self, club_id, new_name):
            self.updates.append((club_id, new_name))

    monkeypatch.setattr(admin_panel_handlers, "ClubRepository", FakeClubRepo)
    message = message_factory(text="  Новый клуб  ")
    state = state_factory({"club_id": 8})

    run_async(admin_panel_handlers.admin_edit_club_name(message, state, session=object()))

    assert FakeClubRepo.updates == [(8, "Новый клуб")]
    assert state.cleared is True
    assert message.answers == [{"text": msg.ADMIN_CLUB_UPDATED.format(name="Новый клуб"), "reply_markup": None}]


def test_admin_edit_rating_start_handles_empty_players(monkeypatch, run_async, callback_factory, state_factory):
    class FakePlayerRepo:
        def __init__(self, _session):
            pass

        async def get_all_approved(self):
            return []

    monkeypatch.setattr(admin_panel_handlers, "PlayerRepository", FakePlayerRepo)
    callback = callback_factory(user_id=1004)
    state = state_factory()

    run_async(
        admin_panel_handlers.admin_edit_rating_start(
            callback,
            AdminPanelAction(action="edit_rating"),
            session=object(),
            state=state,
        )
    )

    assert callback.message.answers == [{"text": msg.ADMIN_NO_PLAYERS, "reply_markup": None}]
    assert state.current_state is None


def test_admin_edit_rating_start_stores_rating_field(monkeypatch, run_async, callback_factory, state_factory):
    players = [type("PlayerStub", (), {"id": 1, "first_name": "Ivan", "last_name": "Petrov"})()]

    class FakePlayerRepo:
        def __init__(self, _session):
            pass

        async def get_all_approved(self):
            return players

    monkeypatch.setattr(admin_panel_handlers, "PlayerRepository", FakePlayerRepo)
    callback = callback_factory(user_id=1005)
    state = state_factory()

    run_async(
        admin_panel_handlers.admin_edit_rating_start(
            callback,
            AdminPanelAction(action="edit_prev_rating"),
            session=object(),
            state=state,
        )
    )

    assert callback.message.answers[0]["text"] == msg.ADMIN_CHOOSE_PLAYER
    assert _button_callback_data(callback.message.answers[0]["reply_markup"])[-1] == (
        AdminPanelAction(action="cancel").pack()
    )
    assert state.data["rating_field"] == "edit_prev_rating"
    assert state.current_state == FSMAdminEditRating.choose_player


def test_admin_edit_rating_chosen_uses_prev_rating_prompt(monkeypatch, run_async, callback_factory, state_factory, player_factory):
    player = player_factory(player_id=15)

    class FakePlayerRepo:
        def __init__(self, _session):
            pass

        async def get_by_id(self, player_id):
            assert player_id == 15
            return player

    monkeypatch.setattr(admin_panel_handlers, "PlayerRepository", FakePlayerRepo)
    callback = callback_factory(user_id=1006)
    state = state_factory({"rating_field": "edit_prev_rating"})

    run_async(
        admin_panel_handlers.admin_edit_rating_chosen(
            callback,
            AdminPlayerCallback(player_id=15),
            state,
            session=object(),
        )
    )

    assert state.data["player_id"] == 15
    assert state.current_state == FSMAdminEditRating.enter_rating
    assert callback.message.answers[0]["text"] == msg.ADMIN_ENTER_PREV_RATING.format(name="Ivan Petrov")
    assert _button_callback_data(callback.message.answers[0]["reply_markup"]) == [
        AdminPanelAction(action="cancel").pack()
    ]


def test_admin_edit_rating_value_rejects_invalid_number(run_async, message_factory, state_factory):
    message = message_factory(text="abc")
    state = state_factory({"player_id": 16, "rating_field": "edit_rating"})

    run_async(admin_panel_handlers.admin_edit_rating_value(message, state, session=object()))

    assert message.answers[0]["text"] == msg.ADMIN_INVALID_RATING
    assert _button_callback_data(message.answers[0]["reply_markup"]) == [
        AdminPanelAction(action="cancel").pack()
    ]
    assert state.cleared is False


def test_admin_cancel_action_clears_state_and_returns_panel(run_async, callback_factory, state_factory):
    callback = callback_factory(user_id=1016)
    state = state_factory({"club_id": 8})
    run_async(state.set_state(FSMAdminEditClub.enter_new_name))

    run_async(admin_panel_handlers.admin_cancel_action(callback, state))

    assert state.cleared is True
    assert callback.message.answers[0]["text"] == msg.ADMIN_ACTION_CANCELLED
    assert callback.message.answers[0]["reply_markup"] is not None
    assert callback.answers == [{"text": None, "show_alert": False}]


def test_admin_edit_rating_value_updates_prev_rating(monkeypatch, run_async, message_factory, state_factory, player_factory):
    player = player_factory(player_id=16)

    class FakePlayerRepo:
        update_calls = []

        def __init__(self, _session):
            pass

        async def get_by_id(self, player_id):
            assert player_id == 16
            return player

        async def update_rating_data(self, player_id, **kwargs):
            self.update_calls.append((player_id, kwargs))

    monkeypatch.setattr(admin_panel_handlers, "PlayerRepository", FakePlayerRepo)
    message = message_factory(text="10,5")
    state = state_factory({"player_id": 16, "rating_field": "edit_prev_rating"})

    run_async(admin_panel_handlers.admin_edit_rating_value(message, state, session=object()))

    assert state.cleared is True
    assert FakePlayerRepo.update_calls[0][0] == 16
    assert FakePlayerRepo.update_calls[0][1]["prev_season_rating"] == 10.5
    assert "prev_rating_updated_at" in FakePlayerRepo.update_calls[0][1]
    assert message.answers == [
        {"text": msg.ADMIN_PREV_RATING_UPDATED.format(name="Ivan Petrov", rating=10.5), "reply_markup": None}
    ]


def test_admin_edit_rating_value_updates_current_rating(monkeypatch, run_async, message_factory, state_factory, player_factory):
    player = player_factory(player_id=17)

    class FakePlayerRepo:
        update_calls = []

        def __init__(self, _session):
            pass

        async def get_by_id(self, player_id):
            assert player_id == 17
            return player

        async def update_rating_data(self, player_id, **kwargs):
            self.update_calls.append((player_id, kwargs))

    monkeypatch.setattr(admin_panel_handlers, "PlayerRepository", FakePlayerRepo)
    message = message_factory(text="88.2")
    state = state_factory({"player_id": 17, "rating_field": "edit_rating"})

    run_async(admin_panel_handlers.admin_edit_rating_value(message, state, session=object()))

    assert FakePlayerRepo.update_calls[0][0] == 17
    assert FakePlayerRepo.update_calls[0][1]["current_rating"] == 88.2
    assert "rating_updated_at" in FakePlayerRepo.update_calls[0][1]
    assert message.answers == [
        {"text": msg.ADMIN_RATING_UPDATED.format(name="Ivan Petrov", rating=88.2), "reply_markup": None}
    ]


def test_build_scraped_players_export_includes_rating_columns(run_async):
    tournament = Tournament(id=3, name="Суперлига — Премьер-Лига")
    club = Club(id=5, name="Юнитек", tournament_id=3)
    club.tournament = tournament
    player = ScrapedPlayerStats(
        id=7,
        external_id="ext-7",
        first_name="Ivan",
        last_name="Petrov",
        club_id=5,
        games_played=12,
        mvp_count=2,
        goals=4,
        assists=5,
        yellow_cards=1,
        red_cards=0,
        current_rating=24.5,
        division_rank=8,
        division_total=30,
        avg_points_per_game=2.04,
    )
    player.club = club
    player.created_at = datetime(2026, 6, 28, 10, 0, tzinfo=timezone.utc)
    player.updated_at = datetime(2026, 6, 28, 11, 0, tzinfo=timezone.utc)

    class FakeScalarResult:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

    class FakeSession:
        async def execute(self, _stmt):
            return FakeScalarResult([player])

    filename, payload, row_count = run_async(
        admin_panel_handlers._build_scraped_players_export(FakeSession())
    )

    text = payload.decode("utf-8-sig")
    assert filename.startswith("scraped_players_stats_")
    assert row_count == 1
    assert "current_rating,division_rank,division_total,avg_points_per_game" in text
    assert "24.5,8,30,2.04" in text
    assert "Юнитек" in text
    assert "Суперлига — Премьер-Лига" in text


def test_admin_export_all_players_sends_document(monkeypatch, run_async, callback_factory):
    async def fake_build(_session):
        return "players.csv", b"id,current_rating\n1,12.5\n", 1

    monkeypatch.setattr(admin_panel_handlers, "_build_scraped_players_export", fake_build)
    callback = callback_factory(user_id=1017)

    run_async(admin_panel_handlers.admin_export_all_players(callback, session=object()))

    assert callback.message.documents[0]["caption"] == msg.ADMIN_ALL_PLAYERS_EXPORTED.format(count=1)
    assert callback.message.documents[0]["document"].filename == "players.csv"
    assert callback.answers == [{"text": None, "show_alert": False}]
