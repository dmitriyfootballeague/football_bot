from datetime import datetime, timezone

import pytest

from football_bot.locales import messages as msg
from football_bot.models import PlayerPosition, PlayerRole, RegistrationStatus
from tests.football_bot.e2e.support import (
    _seed_player,
    _seed_tournament_and_club,
)

pytestmark = pytest.mark.e2e


def test_real_e2e_rating_flows(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app
        tournament, club = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Лига рейтинга",
            club_name="Олимп",
        )
        updated_at = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)

        await _seed_player(
            real_e2e_session_pool,
            telegram_id=1501,
            first_name="Current",
            last_name="Player",
            username="current_player",
            role=PlayerRole.PLAYER,
            registration_status=RegistrationStatus.APPROVED,
            club_id=club.id,
            position=PlayerPosition.DEFENDER,
            description="Ball-playing defender",
            current_rating=8.1,
            division_rank=2,
            division_total=12,
            position_rank=1,
            position_total=4,
            avg_points_per_game=6.5,
            rating_updated_at=updated_at,
        )
        await _seed_player(
            real_e2e_session_pool,
            telegram_id=1502,
            first_name="Previous",
            last_name="Agent",
            username="previous_agent",
            role=PlayerRole.FREE_AGENT,
            registration_status=RegistrationStatus.APPROVED,
            club_id=None,
            description="Creative playmaker",
            prev_season_rating=7.4,
            prev_division_rank=3,
            prev_division_total=18,
            prev_position_rank=2,
            prev_position_total=6,
            prev_avg_points=5.9,
            prev_rating_updated_at=updated_at,
        )

        await app.feed_message(
            user_id=1501,
            text_value="Рейтинг",
            first_name="Current",
            username="current_player",
        )
        current_rating_message = app.last_call(chat_id=1501, method="sendMessage")
        current_text = current_rating_message.payload["text"]
        assert "Current Player" in current_text
        assert "Олимп" in current_text
        assert "Лига рейтинга" in current_text
        assert "8.1" in current_text

        await app.feed_message(
            user_id=1502,
            text_value="Рейтинг за прошлый сезон",
            first_name="Previous",
            username="previous_agent",
        )
        prev_rating_message = app.last_call(chat_id=1502, method="sendMessage")
        prev_text = prev_rating_message.payload["text"]
        assert "Previous Agent" in prev_text
        assert "7.4" in prev_text
        assert "Creative playmaker" in prev_text

    run_async(scenario())


def test_real_e2e_instruction_flows(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app

        await app.feed_message(
            user_id=1503,
            text_value="/start",
            first_name="Guest",
            username="guest_user",
        )
        guest_start = app.last_call(chat_id=1503, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1503,
            data="instruction",
            call=guest_start,
            first_name="Guest",
            username="guest_user",
        )

        guest_messages = app.calls_for_chat(1503, method="sendMessage")
        instruction_texts = [call.payload["text"] for call in guest_messages[-3:]]
        assert instruction_texts == [
            msg.INSTRUCTION_CAPTAIN,
            msg.INSTRUCTION_PLAYER,
            msg.INSTRUCTION_FREE_AGENT,
        ]

        await _seed_player(
            real_e2e_session_pool,
            telegram_id=1504,
            first_name="Role",
            last_name="Player",
            username="role_player",
            role=PlayerRole.PLAYER,
            registration_status=RegistrationStatus.APPROVED,
            club_id=None,
        )

        await app.feed_message(
            user_id=1504,
            text_value="/start",
            first_name="Role",
            username="role_player",
        )
        player_start = app.last_call(chat_id=1504, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1504,
            data="instruction",
            call=player_start,
            first_name="Role",
            username="role_player",
        )

        player_instruction = app.last_call(chat_id=1504, method="sendMessage")
        assert player_instruction.payload["text"] == msg.INSTRUCTION_PLAYER

    run_async(scenario())
