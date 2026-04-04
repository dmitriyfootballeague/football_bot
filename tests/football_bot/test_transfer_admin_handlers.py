from football_bot.handlers.admin import transfer_admin_handlers
from football_bot.keyboards.inline.transfer_kb import AdminTransferAction
from football_bot.locales import messages as msg
from football_bot.models import TransferRequest, TransferStatus, TransferType


def test_admin_approve_transfer_returns_alert_when_request_missing(monkeypatch, run_async, callback_factory):
    class FakeTransferService:
        def __init__(self, _session):
            pass

        async def get_request(self, _request_id):
            return None

    monkeypatch.setattr(transfer_admin_handlers, "TransferService", FakeTransferService)
    callback = callback_factory(user_id=910)

    run_async(
        transfer_admin_handlers.admin_approve_transfer(
            callback,
            AdminTransferAction(action="approve", request_id=31),
            session=object(),
        )
    )

    assert callback.answers == [{"text": "Заявка не найдена", "show_alert": True}]
    assert callback.bot.sent_messages == []
    assert callback.message.edited_text == []


def test_admin_approve_exit_notifies_player_and_captain(
    monkeypatch, run_async, callback_factory, player_factory
):
    player = player_factory(player_id=21, telegram_id=2021)
    captain = player_factory(player_id=22, telegram_id=2022)
    from_club = type("ClubStub", (), {"name": "Элит"})()
    request = TransferRequest(
        id=41,
        player_id=21,
        transfer_type=TransferType.EXIT,
        status=TransferStatus.PENDING_ADMIN,
        from_club_id=55,
        to_club_id=None,
        initiated_by=2021,
    )
    request.player = player
    request.from_club = from_club

    class FakeTransferService:
        approved_calls = []

        def __init__(self, _session):
            pass

        async def get_request(self, request_id):
            assert request_id == 41
            return request

        async def admin_approve(self, request_id):
            self.approved_calls.append(request_id)
            request.status = TransferStatus.APPROVED
            return request

        async def get_captain_of_club(self, club_id):
            assert club_id == 55
            return captain

    monkeypatch.setattr(transfer_admin_handlers, "TransferService", FakeTransferService)
    callback = callback_factory(user_id=911)

    run_async(
        transfer_admin_handlers.admin_approve_transfer(
            callback,
            AdminTransferAction(action="approve", request_id=41),
            session=object(),
        )
    )

    assert callback.message.edited_text == [
        {"text": "✅ Трансфер одобрен: Ivan Petrov", "reply_markup": None}
    ]
    assert callback.bot.sent_messages[0]["chat_id"] == 2021
    assert callback.bot.sent_messages[0]["text"] == msg.TRANSFER_EXIT_ADMIN_APPROVED
    assert callback.bot.sent_messages[1]["chat_id"] == 2022
    assert callback.bot.sent_messages[1]["text"] == msg.TRANSFER_EXIT_ADMIN_APPROVED_CAPTAIN.format(
        name="Ivan Petrov"
    )
    assert callback.answers[-1] == {"text": msg.ADMIN_TRANSFER_APPROVED, "show_alert": False}


def test_admin_reject_join_notifies_player_and_target_captain(
    monkeypatch, run_async, callback_factory, player_factory
):
    player = player_factory(player_id=23, telegram_id=2023)
    captain = player_factory(player_id=24, telegram_id=2024)
    to_club = type("ClubStub", (), {"name": "РЖД"})()
    request = TransferRequest(
        id=42,
        player_id=23,
        transfer_type=TransferType.JOIN,
        status=TransferStatus.PENDING_ADMIN,
        from_club_id=None,
        to_club_id=66,
        initiated_by=2023,
    )
    request.player = player
    request.to_club = to_club

    class FakeTransferService:
        reject_calls = []

        def __init__(self, _session):
            pass

        async def get_request(self, request_id):
            assert request_id == 42
            return request

        async def admin_reject(self, request_id):
            self.reject_calls.append(request_id)
            request.status = TransferStatus.REJECTED
            return request

        async def get_captain_of_club(self, club_id):
            assert club_id == 66
            return captain

    monkeypatch.setattr(transfer_admin_handlers, "TransferService", FakeTransferService)
    callback = callback_factory(user_id=912)

    run_async(
        transfer_admin_handlers.admin_reject_transfer(
            callback,
            AdminTransferAction(action="reject", request_id=42),
            session=object(),
        )
    )

    assert callback.message.edited_text == [
        {"text": "❌ Трансфер отклонён: Ivan Petrov", "reply_markup": None}
    ]
    assert callback.bot.sent_messages[0]["chat_id"] == 2023
    assert callback.bot.sent_messages[0]["text"] == msg.TRANSFER_JOIN_ADMIN_REJECTED.format(club="РЖД")
    assert callback.bot.sent_messages[1]["chat_id"] == 2024
    assert callback.bot.sent_messages[1]["text"] == msg.TRANSFER_JOIN_ADMIN_REJECTED_CAPTAIN.format(
        name="Ivan Petrov"
    )
    assert callback.answers[-1] == {"text": msg.ADMIN_TRANSFER_REJECTED, "show_alert": False}


def test_admin_approve_kick_resolves_captain_by_initiator(
    monkeypatch, run_async, callback_factory, player_factory
):
    player = player_factory(player_id=25, telegram_id=2025)
    captain = player_factory(player_id=26, telegram_id=2026)
    from_club = type("ClubStub", (), {"name": "Оптик"})()
    request = TransferRequest(
        id=43,
        player_id=25,
        transfer_type=TransferType.KICK,
        status=TransferStatus.PENDING_ADMIN,
        from_club_id=77,
        to_club_id=None,
        initiated_by=2026,
    )
    request.player = player
    request.from_club = from_club

    class FakeTransferService:
        def __init__(self, _session):
            pass

        async def get_request(self, _request_id):
            return request

        async def admin_approve(self, _request_id):
            request.status = TransferStatus.APPROVED
            return request

        async def get_player_by_telegram_id(self, telegram_id):
            assert telegram_id == 2026
            return captain

    monkeypatch.setattr(transfer_admin_handlers, "TransferService", FakeTransferService)
    callback = callback_factory(user_id=913)

    run_async(
        transfer_admin_handlers.admin_approve_transfer(
            callback,
            AdminTransferAction(action="approve", request_id=43),
            session=object(),
        )
    )

    assert callback.bot.sent_messages[0]["text"] == msg.TRANSFER_KICK_ADMIN_APPROVED.format(club="Оптик")
    assert callback.bot.sent_messages[1]["chat_id"] == 2026
    assert callback.bot.sent_messages[1]["text"] == msg.TRANSFER_KICK_ADMIN_APPROVED_CAPTAIN.format(
        name="Ivan Petrov"
    )
