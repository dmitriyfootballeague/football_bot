from football_bot.service.rating_service import RatingService


def test_get_player_rating_delegates_to_repository(monkeypatch, run_async):
    player = object()

    class FakePlayerRepo:
        calls = []

        def __init__(self, _session):
            pass

        async def get_by_telegram_id(self, telegram_id):
            self.calls.append(telegram_id)
            return player

    monkeypatch.setattr(
        "football_bot.service.rating_service.PlayerRepository",
        FakePlayerRepo,
    )
    svc = RatingService(session=object())

    result = run_async(svc.get_player_rating(12345))

    assert result is player
    assert FakePlayerRepo.calls == [12345]


def test_update_rating_delegates_to_repository(monkeypatch, run_async):
    class FakePlayerRepo:
        calls = []

        def __init__(self, _session):
            pass

        async def update_rating_data(self, player_id, **rating_data):
            self.calls.append((player_id, rating_data))

    monkeypatch.setattr(
        "football_bot.service.rating_service.PlayerRepository",
        FakePlayerRepo,
    )
    svc = RatingService(session=object())

    run_async(svc.update_rating(77, current_rating=10.2, division_rank=3))

    assert FakePlayerRepo.calls == [
        (
            77,
            {
                "current_rating": 10.2,
                "division_rank": 3,
            },
        )
    ]
