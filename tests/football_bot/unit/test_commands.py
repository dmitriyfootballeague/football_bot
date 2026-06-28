from football_bot.handlers import commands
from football_bot.locales import messages as msg
from football_bot.models import RegistrationStatus, PlayerRole


def _button_texts(markup) -> list[str]:
    if hasattr(markup, "keyboard"):
        return [button.text for row in markup.keyboard for button in row]
    if hasattr(markup, "inline_keyboard"):
        return [button.text for row in markup.inline_keyboard for button in row]
    return []


def test_cmd_start_shows_player_menu_for_approved_player(
    monkeypatch, run_async, message_factory, state_factory, player_factory
):
    player = player_factory(
        telegram_id=100,
        first_name="Pavel",
        role=PlayerRole.PLAYER,
        registration_status=RegistrationStatus.APPROVED,
    )

    class FakeRegistrationService:
        def __init__(self, _session):
            pass

        async def get_player(self, telegram_id):
            assert telegram_id == 100
            return player

    monkeypatch.setattr(commands, "RegistrationService", FakeRegistrationService)
    message = message_factory(user_id=100)
    state = state_factory({"some": "state"})

    run_async(commands.cmd_start(message, state, session=object()))

    assert state.cleared is True
    assert message.answers[0]["text"] == "С возвращением, Pavel!"
    assert _button_texts(message.answers[0]["reply_markup"]) == ["Рейтинг", "Трансфер"]


def test_cmd_start_shows_pending_message_for_pending_user(
    monkeypatch, run_async, message_factory, state_factory, player_factory
):
    player = player_factory(
        telegram_id=101,
        registration_status=RegistrationStatus.PENDING,
    )

    class FakeRegistrationService:
        def __init__(self, _session):
            pass

        async def get_player(self, _telegram_id):
            return player

    monkeypatch.setattr(commands, "RegistrationService", FakeRegistrationService)
    message = message_factory(user_id=101)
    state = state_factory()

    run_async(commands.cmd_start(message, state, session=object()))

    assert message.answers == [{"text": msg.NOTIF_REG_PENDING, "reply_markup": None}]


def test_cmd_start_shows_reapply_keyboard_for_rejected_user(
    monkeypatch, run_async, message_factory, state_factory, player_factory
):
    player = player_factory(
        telegram_id=102,
        registration_status=RegistrationStatus.REJECTED,
    )

    class FakeRegistrationService:
        def __init__(self, _session):
            pass

        async def get_player(self, _telegram_id):
            return player

    monkeypatch.setattr(commands, "RegistrationService", FakeRegistrationService)
    message = message_factory(user_id=102)
    state = state_factory()

    run_async(commands.cmd_start(message, state, session=object()))

    assert message.answers[0]["text"] == msg.NOTIF_REG_REJECTED_REAPPLY
    assert _button_texts(message.answers[0]["reply_markup"]) == ["Подать заявку", "Инструкция"]


def test_cmd_start_shows_welcome_for_new_user(monkeypatch, run_async, message_factory, state_factory):
    class FakeRegistrationService:
        def __init__(self, _session):
            pass

        async def get_player(self, _telegram_id):
            return None

    monkeypatch.setattr(commands, "RegistrationService", FakeRegistrationService)
    message = message_factory(user_id=103)
    state = state_factory()

    run_async(commands.cmd_start(message, state, session=object()))

    assert message.answers[0]["text"] == msg.WELCOME_MESSAGE
    assert _button_texts(message.answers[0]["reply_markup"]) == ["Регистрация", "Инструкция"]


def test_cmd_cancel_clears_state_and_replies(run_async, message_factory, state_factory):
    message = message_factory(text="/cancel", user_id=104)
    state = state_factory({"pending": "value"})

    run_async(commands.cmd_cancel(message, state))

    assert state.cleared is True
    assert message.answers == [{"text": "Вы сбросили все действия и состояния.", "reply_markup": None}]


def test_cmd_help_replies_with_available_commands(run_async, message_factory):
    message = message_factory(text="/help", user_id=105)

    run_async(commands.cmd_help(message))

    assert message.answers == [
        {
            "text": "Доступные команды:\n/start - начать\n/cancel - отменить текущее действие",
            "reply_markup": None,
        }
    ]
