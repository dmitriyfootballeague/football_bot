from football_bot.handlers.user import instruction_handler
from football_bot.locales import messages as msg
from football_bot.models import PlayerRole, RegistrationStatus


def test_show_instruction_for_approved_player_role(monkeypatch, run_async, callback_factory, player_factory):
    player = player_factory(
        telegram_id=3001,
        role=PlayerRole.PLAYER,
        registration_status=RegistrationStatus.APPROVED,
    )

    class FakePlayerRepo:
        def __init__(self, _session):
            pass

        async def get_by_telegram_id(self, _telegram_id):
            return player

    monkeypatch.setattr(instruction_handler, "PlayerRepository", FakePlayerRepo)
    callback = callback_factory(user_id=3001, data="instruction")

    run_async(instruction_handler.show_instruction(callback, session=object()))

    assert callback.message.answers == [{"text": msg.INSTRUCTION_PLAYER, "reply_markup": None}]
    assert callback.answers[-1] == {"text": None, "show_alert": False}


def test_show_instruction_for_unapproved_user_shows_all(monkeypatch, run_async, callback_factory, player_factory):
    player = player_factory(
        telegram_id=3002,
        role=PlayerRole.CAPTAIN,
        registration_status=RegistrationStatus.PENDING,
    )

    class FakePlayerRepo:
        def __init__(self, _session):
            pass

        async def get_by_telegram_id(self, _telegram_id):
            return player

    monkeypatch.setattr(instruction_handler, "PlayerRepository", FakePlayerRepo)
    callback = callback_factory(user_id=3002, data="instruction")

    run_async(instruction_handler.show_instruction(callback, session=object()))

    assert callback.message.answers == [
        {"text": msg.INSTRUCTION_CAPTAIN, "reply_markup": None},
        {"text": msg.INSTRUCTION_PLAYER, "reply_markup": None},
        {"text": msg.INSTRUCTION_FREE_AGENT, "reply_markup": None},
    ]


def test_show_instruction_for_unregistered_user_shows_all(monkeypatch, run_async, callback_factory):
    class FakePlayerRepo:
        def __init__(self, _session):
            pass

        async def get_by_telegram_id(self, _telegram_id):
            return None

    monkeypatch.setattr(instruction_handler, "PlayerRepository", FakePlayerRepo)
    callback = callback_factory(user_id=3003, data="instruction")

    run_async(instruction_handler.show_instruction(callback, session=object()))

    assert callback.message.answers == [
        {"text": msg.INSTRUCTION_CAPTAIN, "reply_markup": None},
        {"text": msg.INSTRUCTION_PLAYER, "reply_markup": None},
        {"text": msg.INSTRUCTION_FREE_AGENT, "reply_markup": None},
    ]
