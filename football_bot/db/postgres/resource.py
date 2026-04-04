from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from football_bot.utils.config import DBConfig


def create_pool(settings: DBConfig) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(url=settings.db_dsn)
    pool: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    return pool
