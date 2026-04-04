from types import SimpleNamespace

from football_bot.handlers.user import registration_handlers
from football_bot.keyboards.inline.registration_kb import ClubCallback, PositionCallback, TournamentCallback
from football_bot.locales import messages as msg
from football_bot.models import PlayerPosition, PlayerRole
from football_bot.states import FSMRegistration


def test_process_first_name_rejects_invalid_name(monkeypatch, run_async, message_factory, state_factory):
    monkeypatch.setattr(registration_handlers, "is_valid_name", lambda _text: False)
    message = message_factory(text="12")
    state = state_factory()

    run_async(registration_handlers.process_first_name(message, state))

    assert message.answers == [{"text": msg.ERR_INVALID_NAME, "reply_markup": None}]
    assert state.data == {}
    assert state.current_state is None


def test_process_first_name_accepts_valid_name(monkeypatch, run_async, message_factory, state_factory):
    monkeypatch.setattr(registration_handlers, "is_valid_name", lambda _text: True)
    message = message_factory(text=" Ivan ")
    state = state_factory()

    run_async(registration_handlers.process_first_name(message, state))

    assert state.data["first_name"] == "Ivan"
    assert state.current_state == FSMRegistration.enter_last_name
    assert message.answers == [{"text": msg.REG_ENTER_LAST_NAME, "reply_markup": None}]


def test_process_birth_date_rejects_invalid_value(monkeypatch, run_async, message_factory, state_factory):
    monkeypatch.setattr(registration_handlers, "is_valid_date", lambda _text: False)
    message = message_factory(text="2020-01-01")
    state = state_factory()

    run_async(registration_handlers.process_birth_date(message, state))

    assert message.answers == [{"text": msg.ERR_INVALID_DATE, "reply_markup": None}]
    assert "birth_date" not in state.data


def test_process_birth_date_accepts_valid_value(monkeypatch, run_async, message_factory, state_factory):
    monkeypatch.setattr(registration_handlers, "is_valid_date", lambda _text: True)
    message = message_factory(text="25.03.2000")
    state = state_factory()

    run_async(registration_handlers.process_birth_date(message, state))

    assert state.data["birth_date"] == "2000-03-25"
    assert state.current_state == FSMRegistration.upload_photo
    assert message.answers == [{"text": msg.REG_UPLOAD_PHOTO, "reply_markup": None}]


def test_process_photo_invalid_requires_photo(run_async, message_factory):
    message = message_factory(text="not photo")

    run_async(registration_handlers.process_photo_invalid(message))

    assert message.answers == [{"text": msg.ERR_INVALID_PHOTO, "reply_markup": None}]


def test_process_photo_accepts_largest_photo(run_async, message_factory, state_factory):
    photo = [SimpleNamespace(file_id="small"), SimpleNamespace(file_id="large")]
    message = message_factory(photo=photo)
    state = state_factory()

    run_async(registration_handlers.process_photo(message, state))

    assert state.data["photo_file_id"] == "large"
    assert state.current_state == FSMRegistration.choose_status
    assert message.answers[0]["text"] == msg.REG_CHOOSE_STATUS


def test_status_choose_club_handles_empty_tournament_list(monkeypatch, run_async, callback_factory, state_factory):
    class FakeTournamentRepo:
        def __init__(self, _session):
            pass

        async def get_all(self):
            return []

    monkeypatch.setattr(registration_handlers, "TournamentRepository", FakeTournamentRepo)
    callback = callback_factory(user_id=100)
    state = state_factory()

    run_async(registration_handlers.status_choose_club(callback, state, session=object()))

    assert callback.message.answers == [
        {
            "text": "Турниры ещё не загружены. Попробуйте позже или выберите «Свободный агент».",
            "reply_markup": None,
        }
    ]
    assert state.current_state is None


def test_process_tournament_handles_empty_club_list(monkeypatch, run_async, callback_factory, state_factory):
    class FakeClubRepo:
        def __init__(self, _session):
            pass

        async def get_by_tournament_id(self, tournament_id):
            assert tournament_id == 7
            return []

    monkeypatch.setattr(registration_handlers, "ClubRepository", FakeClubRepo)
    callback = callback_factory(user_id=101)
    state = state_factory()

    run_async(
        registration_handlers.process_tournament(
            callback,
            TournamentCallback(tournament_id=7),
            state,
            session=object(),
        )
    )

    assert state.data["tournament_id"] == 7
    assert callback.message.answers == [{"text": "В этом турнире пока нет клубов.", "reply_markup": None}]


def test_status_free_agent_creates_registration_and_notifies_admins(
    monkeypatch, run_async, callback_factory, state_factory, player_factory
):
    created = player_factory(
        player_id=81,
        telegram_id=5001,
        role=PlayerRole.FREE_AGENT,
        club_id=None,
    )

    class FakeRegistrationService:
        create_calls = []

        def __init__(self, _session):
            pass

        async def create_registration(self, **kwargs):
            self.create_calls.append(kwargs)
            return created

    monkeypatch.setattr(registration_handlers, "RegistrationService", FakeRegistrationService)
    callback = callback_factory(user_id=5001, username="freeagent")
    state = state_factory(
        {
            "first_name": "Ivan",
            "last_name": "Petrov",
            "position": PlayerPosition.DEFENDER.value,
            "description": "desc",
            "birth_date": "2000-01-02",
            "photo_file_id": "photo123",
        }
    )

    run_async(
        registration_handlers.status_free_agent(
            callback,
            state,
            session=object(),
            admin_ids=[1],
            league_admin_ids=[2],
        )
    )

    assert FakeRegistrationService.create_calls[0]["role"] == PlayerRole.FREE_AGENT
    assert callback.message.answers == [{"text": msg.NOTIF_REG_SENT, "reply_markup": None}]
    assert [x["chat_id"] for x in callback.bot.sent_photos] == [1, 2]
    assert state.cleared is True


def test_process_role_creates_player_registration_and_notifies_admins(
    monkeypatch, run_async, callback_factory, state_factory, player_factory
):
    created = player_factory(
        player_id=82,
        telegram_id=5002,
        role=PlayerRole.PLAYER,
        club_id=91,
    )
    club = type("ClubStub", (), {"name": "РЖД"})()

    class FakeRegistrationService:
        create_calls = []

        def __init__(self, _session):
            pass

        async def create_registration(self, **kwargs):
            self.create_calls.append(kwargs)
            return created

    class FakeClubRepo:
        def __init__(self, _session):
            pass

        async def get_by_id(self, club_id):
            assert club_id == 91
            return club

    monkeypatch.setattr(registration_handlers, "RegistrationService", FakeRegistrationService)
    monkeypatch.setattr(registration_handlers, "ClubRepository", FakeClubRepo)
    callback = callback_factory(user_id=5002, username="clubplayer", data="role_player")
    state = state_factory(
        {
            "first_name": "Ivan",
            "last_name": "Petrov",
            "position": PlayerPosition.MIDFIELDER.value,
            "description": None,
            "birth_date": "2000-01-02",
            "photo_file_id": "photo321",
            "club_id": 91,
        }
    )

    run_async(
        registration_handlers.process_role(
            callback,
            state,
            session=object(),
            admin_ids=[1],
            league_admin_ids=[2],
        )
    )

    assert FakeRegistrationService.create_calls[0]["role"] == PlayerRole.PLAYER
    assert FakeRegistrationService.create_calls[0]["club_id"] == 91
    assert callback.message.answers == [{"text": msg.NOTIF_REG_SENT, "reply_markup": None}]
    assert [x["chat_id"] for x in callback.bot.sent_photos] == [1, 2]
    assert state.cleared is True
