from football_bot.handlers.user import registration_handlers
from football_bot.locales import messages as msg
from football_bot.models import RegistrationStatus
from football_bot.states import FSMRegistration


def test_start_registration_blocks_pending_user(monkeypatch, run_async, callback_factory, state_factory, player_factory):
    pending_player = player_factory(
        telegram_id=42,
        registration_status=RegistrationStatus.PENDING,
    )

    class FakeRegistrationService:
        def __init__(self, _session):
            pass

        async def get_player(self, _telegram_id):
            return pending_player

    monkeypatch.setattr(
        registration_handlers,
        "RegistrationService",
        FakeRegistrationService,
    )
    callback = callback_factory(user_id=42)
    state = state_factory()

    run_async(registration_handlers.start_registration(callback, state, session=object()))

    assert callback.answers == [{"text": msg.NOTIF_REG_PENDING_ALERT, "show_alert": True}]
    assert callback.message.answers == []
    assert callback.message.edited_reply_markup == []
    assert state.current_state is None


def test_start_registration_blocks_approved_user(monkeypatch, run_async, callback_factory, state_factory, player_factory):
    approved_player = player_factory(
        telegram_id=43,
        registration_status=RegistrationStatus.APPROVED,
    )

    class FakeRegistrationService:
        def __init__(self, _session):
            pass

        async def get_player(self, _telegram_id):
            return approved_player

    monkeypatch.setattr(
        registration_handlers,
        "RegistrationService",
        FakeRegistrationService,
    )
    callback = callback_factory(user_id=43)
    state = state_factory()

    run_async(registration_handlers.start_registration(callback, state, session=object()))

    assert callback.answers == [{"text": msg.ERR_ALREADY_REGISTERED, "show_alert": True}]
    assert callback.message.answers == []
    assert state.current_state is None


def test_start_registration_allows_rejected_user_to_reapply(monkeypatch, run_async, callback_factory, state_factory, player_factory):
    rejected_player = player_factory(
        telegram_id=44,
        registration_status=RegistrationStatus.REJECTED,
    )

    class FakeRegistrationService:
        def __init__(self, _session):
            pass

        async def get_player(self, _telegram_id):
            return rejected_player

    monkeypatch.setattr(
        registration_handlers,
        "RegistrationService",
        FakeRegistrationService,
    )
    callback = callback_factory(user_id=44)
    state = state_factory()

    run_async(registration_handlers.start_registration(callback, state, session=object()))

    assert callback.message.edited_reply_markup == [None]
    assert callback.message.answers == [{"text": msg.REG_ENTER_FIRST_NAME, "reply_markup": None}]
    assert callback.answers[-1] == {"text": None, "show_alert": False}
    assert state.current_state == FSMRegistration.enter_first_name
