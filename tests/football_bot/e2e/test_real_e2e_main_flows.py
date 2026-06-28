import asyncio
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import date
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
)
from football_bot.middlewares import DBSessionMiddleware
from football_bot.models import (
    Club,
    Player,
    PlayerPosition,
    PlayerRole,
    RegistrationStatus,
    Tournament,
    TransferRequest,
    TransferStatus,
)
from football_bot.repository import PlayerRepository
from football_bot.utils.config import DBConfig


pytestmark = pytest.mark.e2e

ADMIN_IDS = [9001]
LEAGUE_ADMIN_IDS = [9002]


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
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
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

    async def close(self) -> None:
        return None

    async def stream_content(self, *args, **kwargs):
        if False:
            yield b""

    async def make_request(self, bot: Bot, method, timeout: int | None = None):
        payload = method.model_dump(exclude_none=True, warnings=False)
        api_method = method.__api_method__

        if api_method in {"sendMessage", "sendPhoto"}:
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
    )
    pool = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    yield pool
    asyncio.run(engine.dispose())


@pytest.fixture
def real_e2e_app(real_e2e_session_pool):
    async def _truncate() -> None:
        async with real_e2e_session_pool() as session:
            await session.execute(
                text("TRUNCATE TABLE transfer_requests, players, clubs, tournaments RESTART IDENTITY CASCADE")
            )
            await session.commit()

    asyncio.run(_truncate())
    app = RealE2EApp(real_e2e_session_pool)
    yield app
    asyncio.run(app.close())


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
) -> Player:
    async with session_pool() as session:
        player = Player(
            telegram_id=telegram_id,
            telegram_username=username,
            first_name=first_name,
            last_name=last_name,
            position=position,
            description="E2E player",
            birth_date=date(2000, 1, 1),
            photo_file_id=f"photo-{telegram_id}",
            role=role,
            registration_status=registration_status,
            club_id=club_id,
            current_rating=current_rating,
            prev_season_rating=prev_season_rating,
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


def test_real_e2e_registration_free_agent_approval(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app

        await app.feed_message(
            user_id=1001,
            text_value="/start",
            first_name="Ivan",
            username="ivan",
        )
        start_call = app.last_call(chat_id=1001, method="sendMessage")

        await app.feed_callback_from_call(
            user_id=1001,
            data="registration",
            call=start_call,
            first_name="Ivan",
            username="ivan",
        )
        await app.feed_message(user_id=1001, text_value="Ivan", first_name="Ivan", username="ivan")
        await app.feed_message(user_id=1001, text_value="Petrov", first_name="Ivan", username="ivan")

        position_prompt = app.last_call(chat_id=1001, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1001,
            data=PositionCallback(position="forward").pack(),
            call=position_prompt,
            first_name="Ivan",
            username="ivan",
        )

        description_prompt = app.last_call(chat_id=1001, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1001,
            data="skip",
            call=description_prompt,
            first_name="Ivan",
            username="ivan",
        )
        await app.feed_message(user_id=1001, text_value="01.02.2000", first_name="Ivan", username="ivan")
        await app.feed_message(
            user_id=1001,
            photo_file_id="photo-real-e2e",
            first_name="Ivan",
            username="ivan",
        )

        status_prompt = app.last_call(chat_id=1001, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1001,
            data="status_free_agent",
            call=status_prompt,
            first_name="Ivan",
            username="ivan",
        )

        player = await _get_player_by_telegram_id(real_e2e_session_pool, 1001)
        assert player is not None
        assert player.first_name == "Ivan"
        assert player.last_name == "Petrov"
        assert player.position == PlayerPosition.FORWARD
        assert player.role == PlayerRole.FREE_AGENT
        assert player.registration_status == RegistrationStatus.PENDING

        admin_notice = app.last_call(chat_id=9001, method="sendPhoto")
        league_notice = app.last_call(chat_id=9002, method="sendPhoto")
        assert admin_notice.response_caption is not None
        assert league_notice.response_caption is not None

        await app.feed_callback_from_call(
            user_id=9001,
            data=AdminRegAction(action="approve", player_id=player.id).pack(),
            call=admin_notice,
            first_name="Admin",
            username="admin",
        )

        player = await _get_player_by_telegram_id(real_e2e_session_pool, 1001)
        assert player is not None
        assert player.registration_status == RegistrationStatus.APPROVED

        approval_message = app.last_call(chat_id=1001, method="sendMessage")
        assert "одобр" in approval_message.payload["text"].lower()

    run_async(scenario())


def test_real_e2e_transfer_join_flow(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app
        tournament, club = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Суперлига",
            club_name="РЖД",
        )
        await _seed_player(
            real_e2e_session_pool,
            telegram_id=1102,
            first_name="Captain",
            last_name="Club",
            username="captain_club",
            role=PlayerRole.CAPTAIN,
            registration_status=RegistrationStatus.APPROVED,
            club_id=club.id,
            current_rating=9.2,
        )
        free_agent = await _seed_player(
            real_e2e_session_pool,
            telegram_id=1101,
            first_name="Pavel",
            last_name="Free",
            username="pavel_free",
            role=PlayerRole.FREE_AGENT,
            registration_status=RegistrationStatus.APPROVED,
            club_id=None,
            prev_season_rating=7.8,
        )

        await app.feed_message(
            user_id=1101,
            text_value="/start",
            first_name="Pavel",
            username="pavel_free",
        )
        await app.feed_message(
            user_id=1101,
            text_value="Трансфер",
            first_name="Pavel",
            username="pavel_free",
        )
        transfer_menu = app.last_call(chat_id=1101, method="sendMessage")

        await app.feed_callback_from_call(
            user_id=1101,
            data=TransferActionCallback(action="join").pack(),
            call=transfer_menu,
            first_name="Pavel",
            username="pavel_free",
        )

        tournament_prompt = app.last_call(chat_id=1101, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1101,
            data=TournamentCallback(tournament_id=tournament.id).pack(),
            call=tournament_prompt,
            first_name="Pavel",
            username="pavel_free",
        )

        club_prompt = app.last_call(chat_id=1101, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1101,
            data=ClubCallback(club_id=club.id).pack(),
            call=club_prompt,
            first_name="Pavel",
            username="pavel_free",
        )

        request = await _get_transfer_for_player(real_e2e_session_pool, free_agent.id)
        assert request.status == TransferStatus.PENDING_CAPTAIN
        assert request.to_club_id == club.id

        captain_notice = app.last_call(chat_id=1102, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1102,
            data=TransferDecisionCallback(request_id=request.id, action="approve").pack(),
            call=captain_notice,
            first_name="Captain",
            username="captain_club",
        )

        request = await _get_transfer_for_player(real_e2e_session_pool, free_agent.id)
        assert request.status == TransferStatus.PENDING_PLAYER_CONFIRM

        confirm_notice = app.last_call(chat_id=1101, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1101,
            data=TransferDecisionCallback(request_id=request.id, action="confirm").pack(),
            call=confirm_notice,
            first_name="Pavel",
            username="pavel_free",
        )

        request = await _get_transfer_for_player(real_e2e_session_pool, free_agent.id)
        assert request.status == TransferStatus.PENDING_ADMIN

        admin_notice = app.last_call(chat_id=9001, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=9001,
            data=AdminTransferAction(action="approve", request_id=request.id).pack(),
            call=admin_notice,
            first_name="Admin",
            username="admin",
        )

        updated_player = await _get_player_by_telegram_id(real_e2e_session_pool, 1101)
        assert updated_player is not None
        assert updated_player.club_id == club.id
        assert updated_player.role == PlayerRole.PLAYER

    run_async(scenario())


def test_real_e2e_transfer_exit_flow(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app
        _, club = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Премьер дивизион",
            club_name="Элит",
        )
        await _seed_player(
            real_e2e_session_pool,
            telegram_id=1202,
            first_name="Captain",
            last_name="Elite",
            username="captain_elite",
            role=PlayerRole.CAPTAIN,
            registration_status=RegistrationStatus.APPROVED,
            club_id=club.id,
            current_rating=9.0,
        )
        player = await _seed_player(
            real_e2e_session_pool,
            telegram_id=1201,
            first_name="Roman",
            last_name="Leave",
            username="roman_leave",
            role=PlayerRole.PLAYER,
            registration_status=RegistrationStatus.APPROVED,
            club_id=club.id,
            current_rating=6.7,
        )

        await app.feed_message(
            user_id=1201,
            text_value="Трансфер",
            first_name="Roman",
            username="roman_leave",
        )
        transfer_menu = app.last_call(chat_id=1201, method="sendMessage")

        await app.feed_callback_from_call(
            user_id=1201,
            data=TransferActionCallback(action="exit").pack(),
            call=transfer_menu,
            first_name="Roman",
            username="roman_leave",
        )

        request = await _get_transfer_for_player(real_e2e_session_pool, player.id)
        assert request.status == TransferStatus.PENDING_CAPTAIN
        assert request.from_club_id == club.id

        captain_notice = app.last_call(chat_id=1202, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1202,
            data=TransferDecisionCallback(request_id=request.id, action="approve").pack(),
            call=captain_notice,
            first_name="Captain",
            username="captain_elite",
        )

        request = await _get_transfer_for_player(real_e2e_session_pool, player.id)
        assert request.status == TransferStatus.PENDING_ADMIN

        admin_notice = app.last_call(chat_id=9001, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=9001,
            data=AdminTransferAction(action="approve", request_id=request.id).pack(),
            call=admin_notice,
            first_name="Admin",
            username="admin",
        )

        updated_player = await _get_player_by_telegram_id(real_e2e_session_pool, 1201)
        assert updated_player is not None
        assert updated_player.club_id is None
        assert updated_player.role == PlayerRole.FREE_AGENT

    run_async(scenario())


def test_real_e2e_admin_panel_edit_flows(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app
        _, club = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Лига",
            club_name="Старое имя",
        )
        player = await _seed_player(
            real_e2e_session_pool,
            telegram_id=1301,
            first_name="Maksim",
            last_name="Rated",
            username="maksim_rated",
            role=PlayerRole.PLAYER,
            registration_status=RegistrationStatus.APPROVED,
            club_id=club.id,
            current_rating=5.5,
            prev_season_rating=4.4,
        )

        await app.feed_message(
            user_id=9001,
            text_value="/admin",
            first_name="Admin",
            username="admin",
        )
        panel_message = app.last_call(chat_id=9001, method="sendMessage")

        await app.feed_callback_from_call(
            user_id=9001,
            data=AdminPanelAction(action="edit_club").pack(),
            call=panel_message,
            first_name="Admin",
            username="admin",
        )
        clubs_prompt = app.last_call(chat_id=9001, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=9001,
            data=AdminClubCallback(club_id=club.id).pack(),
            call=clubs_prompt,
            first_name="Admin",
            username="admin",
        )
        await app.feed_message(
            user_id=9001,
            text_value="Новое имя клуба",
            first_name="Admin",
            username="admin",
        )

        updated_club = await _get_club(real_e2e_session_pool, club.id)
        assert updated_club.name == "Новое имя клуба"

        await app.feed_message(
            user_id=9001,
            text_value="/admin",
            first_name="Admin",
            username="admin",
        )
        panel_message = app.last_call(chat_id=9001, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=9001,
            data=AdminPanelAction(action="edit_rating").pack(),
            call=panel_message,
            first_name="Admin",
            username="admin",
        )
        players_prompt = app.last_call(chat_id=9001, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=9001,
            data=AdminPlayerCallback(player_id=player.id).pack(),
            call=players_prompt,
            first_name="Admin",
            username="admin",
        )
        await app.feed_message(
            user_id=9001,
            text_value="8.8",
            first_name="Admin",
            username="admin",
        )

        rated_player = await _get_player_by_telegram_id(real_e2e_session_pool, 1301)
        assert rated_player is not None
        assert rated_player.current_rating == 8.8

        await app.feed_message(
            user_id=9001,
            text_value="/admin",
            first_name="Admin",
            username="admin",
        )
        panel_message = app.last_call(chat_id=9001, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=9001,
            data=AdminPanelAction(action="edit_prev_rating").pack(),
            call=panel_message,
            first_name="Admin",
            username="admin",
        )
        players_prompt = app.last_call(chat_id=9001, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=9001,
            data=AdminPlayerCallback(player_id=player.id).pack(),
            call=players_prompt,
            first_name="Admin",
            username="admin",
        )
        await app.feed_message(
            user_id=9001,
            text_value="7.1",
            first_name="Admin",
            username="admin",
        )

        rated_player = await _get_player_by_telegram_id(real_e2e_session_pool, 1301)
        assert rated_player is not None
        assert rated_player.prev_season_rating == 7.1

    run_async(scenario())
