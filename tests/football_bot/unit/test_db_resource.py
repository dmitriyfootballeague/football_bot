from football_bot.db.postgres.resource import create_pool
from football_bot.utils.config import DBConfig


def test_create_pool_applies_engine_pool_settings(monkeypatch):
    captured = {}

    def fake_create_async_engine(*, url, echo, pool_size, max_overflow, pool_pre_ping, pool_recycle):
        captured.update(
            {
                "url": url,
                "echo": echo,
                "pool_size": pool_size,
                "max_overflow": max_overflow,
                "pool_pre_ping": pool_pre_ping,
                "pool_recycle": pool_recycle,
            }
        )
        return object()

    monkeypatch.setattr(
        "football_bot.db.postgres.resource.create_async_engine",
        fake_create_async_engine,
    )

    settings = DBConfig(
        host="db",
        port=5433,
        username="user",
        password="secret",
        database="football",
        db_pool_size=7,
        db_max_overflow=2,
        db_echo=True,
        db_pool_pre_ping=True,
        db_pool_recycle=321,
    )

    create_pool(settings)

    assert captured["url"] == settings.db_dsn
    assert captured["echo"] is True
    assert captured["pool_size"] == 7
    assert captured["max_overflow"] == 2
    assert captured["pool_pre_ping"] is True
    assert captured["pool_recycle"] == 321
