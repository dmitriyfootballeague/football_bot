from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from football_bot.utils.config import DBConfig


def create_pool(settings: DBConfig) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        url=settings.db_dsn,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=settings.db_pool_pre_ping,
        pool_recycle=settings.db_pool_recycle,
    )
    pool: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    return pool
