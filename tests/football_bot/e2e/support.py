import asyncio
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, Update
from sqlalchemy import select, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from football_bot.handlers import commands
from football_bot.handlers.admin import admin_handlers, admin_panel_handlers, transfer_admin_handlers
from football_bot.handlers.user import (
    instruction_handler,
    rating_handlers,
    registration_handlers,
    transfer_handlers,
)
from football_bot.keyboards.inline.admin_kb import AdminRegAction
from football_bot.keyboards.inline.admin_panel_kb import (
    AdminClubCallback,
    AdminPanelAction,
    AdminPlayerCallback,
)
from football_bot.keyboards.inline.registration_kb import ClubCallback, PositionCallback, TournamentCallback
from football_bot.keyboards.inline.transfer_kb import (
    AdminTransferAction,
    TransferActionCallback,
    TransferDecisionCallback,
    TransferPlayerCallback,
)
from football_bot.locales import messages as msg
from football_bot.middlewares import DBSessionMiddleware
from football_bot.models import (
    Club,
    Player,
    PlayerPosition,
    PlayerRole,
    RegistrationStatus,
    ScrapedPlayerStats,
    Tournament,
    TransferRequest,
    TransferStatus,
)
from football_bot.repository import PlayerRepository
from football_bot.utils.config import DBConfig


pytestmark = pytest.mark.e2e

ADMIN_IDS = [9001]
LEAGUE_ADMIN_IDS = [9002]
REPO_ROOT = Path(__file__).resolve().parents[3]


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _e2e_connection_candidates() -> list[URL]:
    config = DBConfig()
    host = os.environ.get("E2E_POSTGRES_HOST", config.host)
    port = int(os.environ.get("E2E_POSTGRES_PORT", config.port))
    username = os.environ.get("E2E_POSTGRES_USERNAME", config.username)
    password = os.environ.get("E2E_POSTGRES_PASSWORD", config.password)
    admin_db = os.environ.get("E2E_POSTGRES_ADMIN_DB", "postgres")

    candidates = [
        URL.create(
            "postgresql+asyncpg",
            username=username,
            password=password,
            host=host,
            port=port,
            database=admin_db,
        )
    ]

    if "E2E_POSTGRES_HOST" not in os.environ and host == "postgres":
        for fallback_host in ("127.0.0.1", "localhost"):
            candidates.append(
                URL.create(
                    "postgresql+asyncpg",
                    username=username,
                    password=password,
                    host=fallback_host,
                    port=port,
                    database=admin_db,
                )
            )

    return candidates


async def _can_connect(url: URL) -> bool:
    conn = None
    try:
        conn = await asyncpg.connect(
            user=url.username,
            password=url.password,
            database=url.database,
            host=url.host,
            port=url.port,
        )
        return True
    except Exception:
        return False
    finally:
        if conn is not None:
            await conn.close()


async def _create_database(url: URL, database_name: str) -> None:
    conn = await asyncpg.connect(
        user=url.username,
        password=url.password,
        database=url.database,
        host=url.host,
        port=url.port,
    )
    try:
        await conn.execute(f'CREATE DATABASE "{database_name}"')
    finally:
        await conn.close()


async def _drop_database(url: URL, database_name: str) -> None:
    conn = await asyncpg.connect(
        user=url.username,
        password=url.password,
        database=url.database,
        host=url.host,
        port=url.port,
    )
    try:
        try:
            await conn.execute(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
        except Exception:
            await conn.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = $1 AND pid <> pg_backend_pid()
                """,
                database_name,
            )
            await conn.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
    finally:
        await conn.close()


def _run_migrations(url: URL) -> None:
    env = os.environ.copy()
    env.update(
        {
            "POSTGRES_HOST": str(url.host),
            "POSTGRES_PORT": str(url.port),
            "POSTGRES_USERNAME": str(url.username),
            "POSTGRES_PASSWORD": str(url.password),
            "POSTGRES_DB": str(url.database),
        }
    )

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            "Failed to prepare E2E database via Alembic.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def _build_dispatcher(session_pool):
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_routers(
        commands.router,
        registration_handlers.router,
        instruction_handler.router,
        rating_handlers.router,
        transfer_handlers.router,
        admin_handlers.router,
        transfer_admin_handlers.router,
        admin_panel_handlers.router,
    )
    dp.update.middleware(DBSessionMiddleware(session_pool=session_pool))
    dp.workflow_data.update(
        {
            "admin_ids": ADMIN_IDS,
            "league_admin_ids": LEAGUE_ADMIN_IDS,
        }
    )
    return dp


@dataclass
class OutboundCall:
    method: str
    payload: dict[str, Any]
    response_message_id: int | None
    response_text: str | None
    response_caption: str | None

    @property
    def chat_id(self) -> int | None:
        value = self.payload.get("chat_id")
        return int(value) if value is not None else None


class RecordingTelegramSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[OutboundCall] = []
        self._message_id = 10_000

    def reset(self) -> None:
        self.calls.clear()
        self._message_id = 10_000

    async def close(self) -> None:
        return None

    async def stream_content(self, *args, **kwargs):
        if False:
            yield b""

    async def make_request(self, bot: Bot, method, timeout: int | None = None):
        payload = method.model_dump(exclude_none=True, warnings=False)
        api_method = method.__api_method__

        if api_method in {"sendMessage", "sendPhoto", "sendDocument"}:
            response = self._build_message(
                bot_id=bot.id,
                chat_id=int(payload["chat_id"]),
                text=payload.get("text"),
                caption=payload.get("caption"),
            )
            self.calls.append(
                OutboundCall(
                    method=api_method,
                    payload=payload,
                    response_message_id=response.message_id,
                    response_text=response.text,
                    response_caption=response.caption,
                )
            )
            return response

        if api_method in {
            "answerCallbackQuery",
            "deleteWebhook",
            "editMessageCaption",
            "editMessageReplyMarkup",
            "editMessageText",
        }:
            self.calls.append(
                OutboundCall(
                    method=api_method,
                    payload=payload,
                    response_message_id=None,
                    response_text=None,
                    response_caption=None,
                )
            )
            return True

        raise AssertionError(f"Unsupported Telegram API method in E2E test: {api_method}")

    def _build_message(
        self,
        *,
        bot_id: int,
        chat_id: int,
        text: str | None = None,
        caption: str | None = None,
    ) -> Message:
        self._message_id += 1
        payload = {
            "message_id": self._message_id,
            "date": int(time.time()),
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": bot_id, "is_bot": True, "first_name": "E2E Bot"},
        }
        if text is not None:
            payload["text"] = text
        if caption is not None:
            payload["caption"] = caption
        return Message.model_validate(payload)


class RealE2EApp:
    def __init__(self, session_pool):
        self.telegram = RecordingTelegramSession()
        self.bot = Bot(
            token="42:TEST",
            session=self.telegram,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self.dp = _build_dispatcher(session_pool)
        self._update_id = 1
        self._user_message_ids: dict[int, int] = {}

    async def close(self) -> None:
        await self.dp.storage.close()
        await self.bot.session.close()

    def reset(self) -> None:
        self.telegram.reset()
        self._update_id = 1
        self._user_message_ids.clear()

        storage = getattr(self.dp.storage, "storage", None)
        if storage is not None:
            storage.clear()

    def _next_update_id(self) -> int:
        value = self._update_id
        self._update_id += 1
        return value

    def _next_user_message_id(self, chat_id: int) -> int:
        current = self._user_message_ids.get(chat_id, 0) + 1
        self._user_message_ids[chat_id] = current
        return current

    async def feed_message(
        self,
        *,
        user_id: int,
        text_value: str | None = None,
        photo_file_id: str | None = None,
        first_name: str = "User",
        username: str | None = None,
    ) -> None:
        message_payload = {
            "message_id": self._next_user_message_id(user_id),
            "date": int(time.time()),
            "chat": {"id": user_id, "type": "private"},
            "from": {
                "id": user_id,
                "is_bot": False,
                "first_name": first_name,
            },
        }
        if username is not None:
            message_payload["from"]["username"] = username
        if text_value is not None:
            message_payload["text"] = text_value
        if photo_file_id is not None:
            message_payload["photo"] = [
                {
                    "file_id": photo_file_id,
                    "file_unique_id": f"{photo_file_id}-uniq",
                    "width": 100,
                    "height": 100,
                }
            ]
        update = Update.model_validate(
            {
                "update_id": self._next_update_id(),
                "message": message_payload,
            }
        )
        await self.dp.feed_update(self.bot, update)

    async def feed_callback_from_call(
        self,
        *,
        user_id: int,
        data: str,
        call: OutboundCall,
        first_name: str = "User",
        username: str | None = None,
    ) -> None:
        message_payload = {
            "message_id": call.response_message_id,
            "date": int(time.time()),
            "chat": {"id": call.chat_id, "type": "private"},
            "from": {"id": self.bot.id, "is_bot": True, "first_name": "E2E Bot"},
        }
        if call.response_text is not None:
            message_payload["text"] = call.response_text
        if call.response_caption is not None:
            message_payload["caption"] = call.response_caption

        callback_payload = {
            "id": str(self._next_update_id()),
            "from": {
                "id": user_id,
                "is_bot": False,
                "first_name": first_name,
            },
            "chat_instance": f"chat-{user_id}",
            "data": data,
            "message": message_payload,
        }
        if username is not None:
            callback_payload["from"]["username"] = username

        update = Update.model_validate(
            {
                "update_id": self._next_update_id(),
                "callback_query": callback_payload,
            }
        )
        await self.dp.feed_update(self.bot, update)

    def last_call(self, *, chat_id: int | None = None, method: str | None = None) -> OutboundCall:
        for call in reversed(self.telegram.calls):
            if chat_id is not None and call.chat_id != chat_id:
                continue
            if method is not None and call.method != method:
                continue
            return call
        raise AssertionError(f"No outbound call matched chat_id={chat_id}, method={method}")

    def calls_for_chat(self, chat_id: int, method: str | None = None) -> list[OutboundCall]:
        matched = [call for call in self.telegram.calls if call.chat_id == chat_id]
        if method is not None:
            matched = [call for call in matched if call.method == method]
        return matched


@pytest.fixture(scope="session")
def real_e2e_database_url():
    if not _is_truthy(os.environ.get("RUN_REAL_E2E_TESTS")):
        pytest.skip("Real E2E tests are disabled. Set RUN_REAL_E2E_TESTS=1 to enable them.")

    chosen_url = None
    for candidate in _e2e_connection_candidates():
        if asyncio.run(_can_connect(candidate)):
            chosen_url = candidate
            break

    if chosen_url is None:
        pytest.skip(
            "Postgres for real E2E tests is unreachable. "
            "If you run tests from the host, set E2E_POSTGRES_HOST=127.0.0.1."
        )

    database_name = f"football_bot_e2e_{uuid.uuid4().hex[:8]}"
    test_url = chosen_url.set(database=database_name)

    asyncio.run(_create_database(chosen_url, database_name))
    try:
        _run_migrations(test_url)
        yield test_url
    finally:
        asyncio.run(_drop_database(chosen_url, database_name))


@pytest.fixture(scope="session")
def real_e2e_session_pool(real_e2e_database_url):
    engine = create_async_engine(
        real_e2e_database_url.render_as_string(hide_password=False),
        echo=False,
        pool_pre_ping=True,
        poolclass=NullPool,
    )
    pool = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    yield pool
    asyncio.run(engine.dispose())


@pytest.fixture(scope="session")
def real_e2e_app_runtime(real_e2e_session_pool):
    app = RealE2EApp(real_e2e_session_pool)
    yield app
    asyncio.run(app.close())


@pytest.fixture
def real_e2e_app(real_e2e_app_runtime, real_e2e_session_pool):
    async def _truncate() -> None:
        async with real_e2e_session_pool() as session:
            await session.execute(
                text(
                    "TRUNCATE TABLE scraped_player_stats, transfer_requests, players, clubs, tournaments "
                    "RESTART IDENTITY CASCADE"
                )
            )
            await session.commit()

    asyncio.run(_truncate())
    real_e2e_app_runtime.reset()
    yield real_e2e_app_runtime


async def _seed_tournament_and_club(session_pool, *, tournament_name: str, club_name: str) -> tuple[Tournament, Club]:
    async with session_pool() as session:
        tournament = Tournament(name=tournament_name)
        club = Club(name=club_name, tournament=tournament)
        session.add_all([tournament, club])
        await session.commit()
        await session.refresh(tournament)
        await session.refresh(club)
        return tournament, club


async def _seed_player(
    session_pool,
    *,
    telegram_id: int,
    first_name: str,
    last_name: str,
    username: str,
    role: PlayerRole,
    registration_status: RegistrationStatus,
    club_id: int | None = None,
    position: PlayerPosition = PlayerPosition.FORWARD,
    current_rating: float | None = None,
    prev_season_rating: float | None = None,
    description: str = "E2E player",
    division_rank: int | None = None,
    division_total: int | None = None,
    position_rank: int | None = None,
    position_total: int | None = None,
    avg_points_per_game: float | None = None,
    rating_updated_at: datetime | None = None,
    prev_division_rank: int | None = None,
    prev_division_total: int | None = None,
    prev_position_rank: int | None = None,
    prev_position_total: int | None = None,
    prev_avg_points: float | None = None,
    prev_rating_updated_at: datetime | None = None,
) -> Player:
    async with session_pool() as session:
        player = Player(
            telegram_id=telegram_id,
            telegram_username=username,
            first_name=first_name,
            last_name=last_name,
            position=position,
            description=description,
            birth_date=date(2000, 1, 1),
            photo_file_id=f"photo-{telegram_id}",
            role=role,
            registration_status=registration_status,
            club_id=club_id,
            current_rating=current_rating,
            division_rank=division_rank,
            division_total=division_total,
            position_rank=position_rank,
            position_total=position_total,
            avg_points_per_game=avg_points_per_game,
            rating_updated_at=rating_updated_at,
            prev_season_rating=prev_season_rating,
            prev_division_rank=prev_division_rank,
            prev_division_total=prev_division_total,
            prev_position_rank=prev_position_rank,
            prev_position_total=prev_position_total,
            prev_avg_points=prev_avg_points,
            prev_rating_updated_at=prev_rating_updated_at,
        )
        session.add(player)
        await session.commit()
        await session.refresh(player)
        return player


async def _seed_scraped_player(
    session_pool,
    *,
    external_id: str,
    first_name: str,
    last_name: str,
    club_id: int | None,
    position: PlayerPosition | None = None,
    games_played: int = 0,
    mvp_count: int = 0,
    goals: int = 0,
    assists: int = 0,
    yellow_cards: int = 0,
    red_cards: int = 0,
    current_rating: float | None = None,
    division_rank: int | None = None,
    division_total: int | None = None,
    avg_points_per_game: float | None = None,
) -> ScrapedPlayerStats:
    async with session_pool() as session:
        player = ScrapedPlayerStats(
            external_id=external_id,
            first_name=first_name,
            last_name=last_name,
            club_id=club_id,
            position=position,
            games_played=games_played,
            mvp_count=mvp_count,
            goals=goals,
            assists=assists,
            yellow_cards=yellow_cards,
            red_cards=red_cards,
            current_rating=current_rating,
            division_rank=division_rank,
            division_total=division_total,
            avg_points_per_game=avg_points_per_game,
        )
        session.add(player)
        await session.commit()
        await session.refresh(player)
        return player


async def _get_player_by_telegram_id(session_pool, telegram_id: int) -> Player | None:
    async with session_pool() as session:
        repo = PlayerRepository(session)
        return await repo.get_by_telegram_id(telegram_id)


async def _get_transfer_for_player(session_pool, player_id: int) -> TransferRequest:
    async with session_pool() as session:
        result = await session.execute(
            select(TransferRequest)
            .where(TransferRequest.player_id == player_id)
            .order_by(TransferRequest.id.desc())
        )
        request = result.scalar_one_or_none()
        if request is None:
            raise AssertionError(f"Transfer request for player_id={player_id} not found")
        return request


async def _get_club(session_pool, club_id: int) -> Club:
    async with session_pool() as session:
        club = await session.get(Club, club_id)
        if club is None:
            raise AssertionError(f"Club id={club_id} not found")
        return club

async def _get_transfer_by_id(session_pool, request_id: int) -> TransferRequest:
    async with session_pool() as session:
        result = await session.execute(
            select(TransferRequest).where(TransferRequest.id == request_id)
        )
        request = result.scalar_one_or_none()
        if request is None:
            raise AssertionError(f"Transfer request id={request_id} not found")
        return request


async def _seed_transfer_request(
    session_pool,
    *,
    player_id: int,
    transfer_type,
    status,
    initiated_by: int,
    from_club_id: int | None = None,
    to_club_id: int | None = None,
    rejected_by: str | None = None,
) -> TransferRequest:
    async with session_pool() as session:
        request = TransferRequest(
            player_id=player_id,
            transfer_type=transfer_type,
            status=status,
            from_club_id=from_club_id,
            to_club_id=to_club_id,
            initiated_by=initiated_by,
            rejected_by=rejected_by,
        )
        session.add(request)
        await session.commit()
        await session.refresh(request)
        return request


def _button_texts(call: OutboundCall) -> list[str]:
    reply_markup = call.payload.get("reply_markup") or {}
    keyboard = reply_markup.get("keyboard") or reply_markup.get("inline_keyboard") or []
    return [button["text"] for row in keyboard for button in row]


def _last_callback_answer(app: RealE2EApp) -> OutboundCall:
    return app.last_call(method="answerCallbackQuery")


async def _start_registration(app: RealE2EApp, *, user_id: int, first_name: str, username: str) -> OutboundCall:
    await app.feed_message(
        user_id=user_id,
        text_value="/start",
        first_name=first_name,
        username=username,
    )
    start_call = app.last_call(chat_id=user_id, method="sendMessage")
    await app.feed_callback_from_call(
        user_id=user_id,
        data="registration",
        call=start_call,
        first_name=first_name,
        username=username,
    )
    return start_call


async def _complete_registration_profile(
    app: RealE2EApp,
    *,
    user_id: int,
    first_name: str,
    last_name: str,
    username: str,
    position: str,
    description: str | None,
    birth_date: str,
    photo_file_id: str,
) -> OutboundCall:
    await app.feed_message(user_id=user_id, text_value=first_name, first_name=first_name, username=username)
    await app.feed_message(user_id=user_id, text_value=last_name, first_name=first_name, username=username)

    position_prompt = app.last_call(chat_id=user_id, method="sendMessage")
    await app.feed_callback_from_call(
        user_id=user_id,
        data=PositionCallback(position=position).pack(),
        call=position_prompt,
        first_name=first_name,
        username=username,
    )

    description_prompt = app.last_call(chat_id=user_id, method="sendMessage")
    if description is None:
        await app.feed_callback_from_call(
            user_id=user_id,
            data="skip",
            call=description_prompt,
            first_name=first_name,
            username=username,
        )
    else:
        await app.feed_message(
            user_id=user_id,
            text_value=description,
            first_name=first_name,
            username=username,
        )

    await app.feed_message(user_id=user_id, text_value=birth_date, first_name=first_name, username=username)
    await app.feed_message(
        user_id=user_id,
        photo_file_id=photo_file_id,
        first_name=first_name,
        username=username,
    )
    return app.last_call(chat_id=user_id, method="sendMessage")


async def _submit_free_agent_registration(
    app: RealE2EApp,
    *,
    user_id: int,
    first_name: str,
    last_name: str,
    username: str,
    position: str = "forward",
    description: str | None = None,
    birth_date: str = "01.02.2000",
    photo_file_id: str = "photo-free-agent",
) -> None:
    await _start_registration(app, user_id=user_id, first_name=first_name, username=username)
    status_prompt = await _complete_registration_profile(
        app,
        user_id=user_id,
        first_name=first_name,
        last_name=last_name,
        username=username,
        position=position,
        description=description,
        birth_date=birth_date,
        photo_file_id=photo_file_id,
    )
    await app.feed_callback_from_call(
        user_id=user_id,
        data="status_free_agent",
        call=status_prompt,
        first_name=first_name,
        username=username,
    )


async def _submit_club_registration(
    app: RealE2EApp,
    *,
    user_id: int,
    first_name: str,
    last_name: str,
    username: str,
    tournament_id: int,
    club_id: int,
    role: str,
    position: str = "forward",
    description: str | None = None,
    birth_date: str = "01.02.2000",
    photo_file_id: str = "photo-club-player",
) -> None:
    await _start_registration(app, user_id=user_id, first_name=first_name, username=username)
    status_prompt = await _complete_registration_profile(
        app,
        user_id=user_id,
        first_name=first_name,
        last_name=last_name,
        username=username,
        position=position,
        description=description,
        birth_date=birth_date,
        photo_file_id=photo_file_id,
    )
    await app.feed_callback_from_call(
        user_id=user_id,
        data="status_choose_club",
        call=status_prompt,
        first_name=first_name,
        username=username,
    )

    tournament_prompt = app.last_call(chat_id=user_id, method="sendMessage")
    await app.feed_callback_from_call(
        user_id=user_id,
        data=TournamentCallback(tournament_id=tournament_id).pack(),
        call=tournament_prompt,
        first_name=first_name,
        username=username,
    )

    club_prompt = app.last_call(chat_id=user_id, method="sendMessage")
    await app.feed_callback_from_call(
        user_id=user_id,
        data=ClubCallback(club_id=club_id).pack(),
        call=club_prompt,
        first_name=first_name,
        username=username,
    )

    role_prompt = app.last_call(chat_id=user_id, method="sendMessage")
    await app.feed_callback_from_call(
        user_id=user_id,
        data=role,
        call=role_prompt,
        first_name=first_name,
        username=username,
    )
