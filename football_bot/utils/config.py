import os
from dataclasses import dataclass

from dotenv import find_dotenv, load_dotenv
from sqlalchemy.engine.url import URL

load_dotenv(find_dotenv())


@dataclass
class DBConfig:
    host: str = os.environ.get("POSTGRES_HOST", "localhost")
    port: int = int(os.environ.get("POSTGRES_PORT", 5432))
    password: str = os.environ.get("POSTGRES_PASSWORD", "postgres")
    username: str = os.environ.get("POSTGRES_USERNAME", "postgres")
    database: str = os.environ.get("POSTGRES_DB", "football_bot")
    db_driver: str = "postgresql+asyncpg"
    db_pool_size: int = 5
    db_max_overflow: int = 0
    db_echo: bool = False
    db_pool_pre_ping: bool = True

    @property
    def db_dsn(self) -> URL:
        return URL.create(
            self.db_driver, self.username, self.password,
            self.host, self.port, self.database,
        )


@dataclass
class RedisConfig:
    host: str = os.environ.get("REDIS_HOST", "localhost")
    port: int = int(os.environ.get("REDIS_PORT", 6379))
    db: int = int(os.environ.get("REDIS_DB", 0))
    use_redis: bool = os.environ.get("USE_REDIS", "False").lower() == "true"


@dataclass
class BotConfig:
    token: str = os.environ.get("BOT_TOKEN", "")
    admin_ids: str = os.environ.get("ADMIN_IDS", "")
    league_admin_ids: str = os.environ.get("LEAGUE_ADMIN_IDS", "")
    scrape_url: str = os.environ.get(
        "SCRAPE_URL",
        "https://olesports.ru/tournament/68fba38cd56d2ba191d6eaee",
    )

    def admin_ids_to_list(self) -> list[int]:
        if not self.admin_ids:
            return []
        return [int(i.strip()) for i in self.admin_ids.split(",")]

    def league_admin_ids_to_list(self) -> list[int]:
        if not self.league_admin_ids:
            return []
        return [int(i.strip()) for i in self.league_admin_ids.split(",")]
