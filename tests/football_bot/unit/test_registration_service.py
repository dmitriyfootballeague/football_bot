from datetime import date

from football_bot.models import PlayerPosition, PlayerRole, RegistrationStatus
from football_bot.service.registration_service import RegistrationService


def test_is_registered_only_for_pending_or_approved(monkeypatch, run_async, player_factory):
    players = {
        1: player_factory(
            telegram_id=1,
            registration_status=RegistrationStatus.PENDING,
        ),
        2: player_factory(
            telegram_id=2,
            registration_status=RegistrationStatus.APPROVED,
        ),
        3: player_factory(
            telegram_id=3,
            registration_status=RegistrationStatus.REJECTED,
        ),
    }

    class FakePlayerRepo:
        def __init__(self, _session):
            pass

        async def get_by_telegram_id(self, telegram_id):
            return players.get(telegram_id)

    monkeypatch.setattr(
        "football_bot.service.registration_service.PlayerRepository",
        FakePlayerRepo,
    )
    svc = RegistrationService(session=object())

    assert run_async(svc.is_registered(1)) is True
    assert run_async(svc.is_registered(2)) is True
    assert run_async(svc.is_registered(3)) is False
    assert run_async(svc.is_registered(999)) is False


def test_create_registration_updates_rejected_player_in_place(monkeypatch, run_async, player_factory):
    existing = player_factory(
        player_id=5,
        telegram_id=77,
        registration_status=RegistrationStatus.REJECTED,
        role=PlayerRole.FREE_AGENT,
        club_id=None,
    )

    class FakePlayerRepo:
        update_calls = []
        created = []

        def __init__(self, _session):
            pass

        async def get_by_telegram_id(self, telegram_id):
            if telegram_id == existing.telegram_id:
                return existing
            return None

        async def update_rating_data(self, player_id, **kwargs):
            self.update_calls.append((player_id, kwargs))
            for key, value in kwargs.items():
                setattr(existing, key, value)

        async def get_by_id(self, player_id):
            assert player_id == existing.id
            return existing

        async def create(self, player):
            self.created.append(player)
            return player

    monkeypatch.setattr(
        "football_bot.service.registration_service.PlayerRepository",
        FakePlayerRepo,
    )
    svc = RegistrationService(session=object())

    result = run_async(
        svc.create_registration(
            telegram_id=77,
            telegram_username="updated_user",
            first_name="Petr",
            last_name="Ivanov",
            position=PlayerPosition.DEFENDER,
            description="new description",
            birth_date=date(1999, 5, 3),
            photo_file_id="new-photo",
            role=PlayerRole.PLAYER,
            club_id=12,
        )
    )

    assert result is existing
    assert FakePlayerRepo.created == []
    assert FakePlayerRepo.update_calls == [
        (
            5,
            {
                "telegram_username": "updated_user",
                "first_name": "Petr",
                "last_name": "Ivanov",
                "position": PlayerPosition.DEFENDER,
                "description": "new description",
                "birth_date": date(1999, 5, 3),
                "photo_file_id": "new-photo",
                "role": PlayerRole.PLAYER,
                "club_id": 12,
                "registration_status": RegistrationStatus.PENDING,
            },
        )
    ]
    assert existing.registration_status == RegistrationStatus.PENDING
    assert existing.role == PlayerRole.PLAYER
    assert existing.club_id == 12


def test_create_registration_creates_new_player_for_new_user(monkeypatch, run_async):
    class FakePlayerRepo:
        created = []

        def __init__(self, _session):
            pass

        async def get_by_telegram_id(self, _telegram_id):
            return None

        async def create(self, player):
            self.created.append(player)
            player.id = 99
            return player

    monkeypatch.setattr(
        "football_bot.service.registration_service.PlayerRepository",
        FakePlayerRepo,
    )
    svc = RegistrationService(session=object())

    created = run_async(
        svc.create_registration(
            telegram_id=100,
            telegram_username="new_user",
            first_name="Sergey",
            last_name="Sidorov",
            position=PlayerPosition.FORWARD,
            description=None,
            birth_date=date(2001, 1, 2),
            photo_file_id="photo",
            role=PlayerRole.FREE_AGENT,
            club_id=None,
        )
    )

    assert len(FakePlayerRepo.created) == 1
    assert created.telegram_id == 100
    assert created.registration_status == RegistrationStatus.PENDING
    assert created.role == PlayerRole.FREE_AGENT
