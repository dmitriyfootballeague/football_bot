from datetime import date as real_date, datetime, timezone

from football_bot.handlers.user import rating_handlers
from football_bot.locales import messages as msg
from football_bot.models import RegistrationStatus


class FakeDate:
    @staticmethod
    def today():
        return real_date(2026, 3, 25)


def test_show_rating_unavailable_for_missing_player(monkeypatch, run_async, message_factory):
    class FakeRatingService:
        def __init__(self, _session):
            pass

        async def get_player_rating(self, _telegram_id):
            return None

    monkeypatch.setattr(rating_handlers, "RatingService", FakeRatingService)
    message = message_factory(text="Рейтинг", user_id=2001)

    run_async(rating_handlers.show_rating(message, session=object()))

    assert message.answers == [{"text": msg.RATING_UNAVAILABLE, "reply_markup": None}]


def test_show_rating_renders_current_rating(monkeypatch, run_async, message_factory, player_factory):
    monkeypatch.setattr(rating_handlers, "date", FakeDate)
    player = player_factory(
        telegram_id=2002,
        registration_status=RegistrationStatus.APPROVED,
        club_id=50,
        current_rating=12.3,
        description="Полезный игрок",
    )
    player.division_rank = 2
    player.division_total = 12
    player.position_rank = 1
    player.position_total = 4
    player.avg_points_per_game = 3.5
    player.rating_updated_at = datetime(2026, 3, 20, tzinfo=timezone.utc)
    player.birth_date = real_date(2000, 3, 25)
    club = type(
        "ClubStub",
        (),
        {
            "name": "Элит",
            "tournament": type("TournamentStub", (), {"name": "Высший"})(),
        },
    )()

    class FakeRatingService:
        def __init__(self, _session):
            pass

        async def get_player_rating(self, _telegram_id):
            return player

    class FakeClubRepo:
        def __init__(self, _session):
            pass

        async def get_by_id(self, club_id):
            assert club_id == 50
            return club

    monkeypatch.setattr(rating_handlers, "RatingService", FakeRatingService)
    monkeypatch.setattr(rating_handlers, "ClubRepository", FakeClubRepo)
    message = message_factory(text="Рейтинг", user_id=2002)

    run_async(rating_handlers.show_rating(message, session=object()))

    text = message.answers[0]["text"]
    assert "Имя: Ivan Petrov" in text
    assert "Возраст: 26" in text
    assert "Футбольный клуб: Элит" in text
    assert "Турнир: Высший" in text
    assert "Ваш текущий рейтинг: <b>12.3</b>" in text
    assert "Дата последнего обновления: <b>20.03.2026</b>" in text


def test_show_prev_rating_renders_previous_season_fields(monkeypatch, run_async, message_factory, player_factory):
    monkeypatch.setattr(rating_handlers, "date", FakeDate)
    player = player_factory(
        telegram_id=2003,
        registration_status=RegistrationStatus.APPROVED,
        club_id=None,
        prev_season_rating=8.8,
        description=None,
    )
    player.prev_division_rank = 3
    player.prev_division_total = 20
    player.prev_position_rank = 2
    player.prev_position_total = 5
    player.prev_avg_points = 1.7
    player.prev_rating_updated_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    player.birth_date = real_date(2001, 1, 10)

    class FakeRatingService:
        def __init__(self, _session):
            pass

        async def get_player_rating(self, _telegram_id):
            return player

    monkeypatch.setattr(rating_handlers, "RatingService", FakeRatingService)
    message = message_factory(text="Рейтинг за прошлый сезон", user_id=2003)

    run_async(rating_handlers.show_prev_rating(message, session=object()))

    text = message.answers[0]["text"]
    assert "Имя: Ivan Petrov" in text
    assert "Возраст: 25" in text
    assert "Описание: —" in text
    assert "Ваш рейтинг за прошлый сезон: <b>8.8</b>" in text
    assert "Дата последнего обновления: <b>01.03.2026</b>" in text


def test_show_prev_rating_unavailable_for_unapproved_player(monkeypatch, run_async, message_factory, player_factory):
    player = player_factory(
        telegram_id=2004,
        registration_status=RegistrationStatus.PENDING,
    )

    class FakeRatingService:
        def __init__(self, _session):
            pass

        async def get_player_rating(self, _telegram_id):
            return player

    monkeypatch.setattr(rating_handlers, "RatingService", FakeRatingService)
    message = message_factory(text="Рейтинг за прошлый сезон", user_id=2004)

    run_async(rating_handlers.show_prev_rating(message, session=object()))

    assert message.answers == [{"text": msg.RATING_UNAVAILABLE, "reply_markup": None}]
