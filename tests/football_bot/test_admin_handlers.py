from football_bot.handlers.admin import admin_handlers
from football_bot.keyboards.inline.admin_kb import AdminRegAction
from football_bot.locales import messages as msg
from football_bot.models import PlayerRole, RegistrationStatus


def test_approve_registration_returns_alert_when_player_missing(monkeypatch, run_async, callback_factory):
    class FakePlayerRepo:
        def __init__(self, _session):
            pass

        async def get_by_id(self, _player_id):
            return None

    monkeypatch.setattr(admin_handlers, "PlayerRepository", FakePlayerRepo)
    callback = callback_factory(user_id=900)

    run_async(
        admin_handlers.approve_registration(
            callback,
            AdminRegAction(action="approve", player_id=11),
            session=object(),
        )
    )

    assert callback.answers == [{"text": "Игрок не найден", "show_alert": True}]
    assert callback.bot.sent_messages == []
    assert callback.message.edited_caption == []


def test_approve_registration_for_free_agent_sends_free_agent_menu(
    monkeypatch, run_async, callback_factory, player_factory
):
    player = player_factory(
        player_id=12,
        telegram_id=1012,
        role=PlayerRole.FREE_AGENT,
        club_id=None,
        registration_status=RegistrationStatus.PENDING,
    )

    class FakePlayerRepo:
        status_updates = []

        def __init__(self, _session):
            pass

        async def get_by_id(self, player_id):
            assert player_id == 12
            return player

        async def update_registration_status(self, player_id, status):
            self.status_updates.append((player_id, status))

    monkeypatch.setattr(admin_handlers, "PlayerRepository", FakePlayerRepo)
    callback = callback_factory(user_id=901)

    run_async(
        admin_handlers.approve_registration(
            callback,
            AdminRegAction(action="approve", player_id=12),
            session=object(),
        )
    )

    assert FakePlayerRepo.status_updates == [(12, RegistrationStatus.APPROVED)]
    sent = callback.bot.sent_messages[0]
    assert sent["chat_id"] == 1012
    assert msg.NOTIF_REG_APPROVED.format(status="Свободный агент") == sent["text"]
    assert sent["reply_markup"] is not None
    assert callback.message.edited_caption == [
        {"caption": "✅ ОДОБРЕНО: Ivan Petrov", "reply_markup": None}
    ]
    assert callback.answers[-1] == {"text": "Регистрация подтверждена", "show_alert": False}


def test_approve_registration_for_club_player_uses_club_name(
    monkeypatch, run_async, callback_factory, player_factory
):
    player = player_factory(
        player_id=13,
        telegram_id=1013,
        role=PlayerRole.PLAYER,
        club_id=55,
        registration_status=RegistrationStatus.PENDING,
    )
    club = type("ClubStub", (), {"name": "Элит"})()

    class FakePlayerRepo:
        def __init__(self, _session):
            pass

        async def get_by_id(self, _player_id):
            return player

        async def update_registration_status(self, _player_id, _status):
            pass

    class FakeClubRepo:
        def __init__(self, _session):
            pass

        async def get_by_id(self, club_id):
            assert club_id == 55
            return club

    monkeypatch.setattr(admin_handlers, "PlayerRepository", FakePlayerRepo)
    monkeypatch.setattr(admin_handlers, "ClubRepository", FakeClubRepo)
    callback = callback_factory(user_id=902)

    run_async(
        admin_handlers.approve_registration(
            callback,
            AdminRegAction(action="approve", player_id=13),
            session=object(),
        )
    )

    sent = callback.bot.sent_messages[0]
    assert sent["chat_id"] == 1013
    assert sent["text"] == msg.NOTIF_REG_APPROVED.format(status="Игрок клуба: Элит")


def test_reject_registration_marks_rejected_and_notifies_player(
    monkeypatch, run_async, callback_factory, player_factory
):
    player = player_factory(
        player_id=14,
        telegram_id=1014,
        registration_status=RegistrationStatus.PENDING,
    )

    class FakePlayerRepo:
        status_updates = []

        def __init__(self, _session):
            pass

        async def get_by_id(self, player_id):
            assert player_id == 14
            return player

        async def update_registration_status(self, player_id, status):
            self.status_updates.append((player_id, status))

    monkeypatch.setattr(admin_handlers, "PlayerRepository", FakePlayerRepo)
    callback = callback_factory(user_id=903)

    run_async(
        admin_handlers.reject_registration(
            callback,
            AdminRegAction(action="reject", player_id=14),
            session=object(),
        )
    )

    assert FakePlayerRepo.status_updates == [(14, RegistrationStatus.REJECTED)]
    assert callback.bot.sent_messages[0]["chat_id"] == 1014
    assert callback.bot.sent_messages[0]["text"] == msg.NOTIF_REG_REJECTED
    assert callback.message.edited_caption == [
        {"caption": "❌ ОТКЛОНЕНО: Ivan Petrov", "reply_markup": None}
    ]
    assert callback.answers[-1] == {"text": "Регистрация отклонена", "show_alert": False}
