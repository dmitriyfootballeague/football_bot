import pytest

from football_bot.keyboards.inline.admin_panel_kb import (
    AdminClubCallback,
    AdminPanelAction,
    AdminPlayerCallback,
)
from football_bot.locales import messages as msg
from football_bot.models import PlayerRole, PlayerPosition, RegistrationStatus
from tests.football_bot.e2e.support import (
    _get_club,
    _get_player_by_telegram_id,
    _seed_player,
    _seed_scraped_player,
    _seed_tournament_and_club,
)

pytestmark = pytest.mark.e2e


def test_real_e2e_admin_export_all_players(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app
        _, club = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Экспорт лига",
            club_name="Арсенал",
        )
        await _seed_scraped_player(
            real_e2e_session_pool,
            external_id="scraped-1",
            first_name="Scraped",
            last_name="Player",
            club_id=club.id,
            position=PlayerPosition.DEFENDER,
            games_played=10,
            mvp_count=2,
            goals=1,
            assists=3,
            yellow_cards=1,
            red_cards=0,
            current_rating=8.3,
            division_rank=1,
            division_total=16,
            avg_points_per_game=6.8,
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
            data=AdminPanelAction(action="export_all_players").pack(),
            call=panel_message,
            first_name="Admin",
            username="admin",
        )

        export_call = app.last_call(chat_id=9001, method="sendDocument")
        assert export_call.payload["caption"] == msg.ADMIN_ALL_PLAYERS_EXPORTED.format(count=1)
        assert export_call.payload.get("document") is not None

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


def test_real_e2e_admin_cancel_resets_edit_flow(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app
        _, club = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Отмена админ",
            club_name="Без изменений",
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

        rename_prompt = app.last_call(chat_id=9001, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=9001,
            data=AdminPanelAction(action="cancel").pack(),
            call=rename_prompt,
            first_name="Admin",
            username="admin",
        )

        cancel_notice = app.last_call(chat_id=9001, method="sendMessage")
        assert cancel_notice.payload["text"] == msg.ADMIN_ACTION_CANCELLED

        call_count_before_text = len(app.telegram.calls)
        await app.feed_message(
            user_id=9001,
            text_value="Не должно сохраниться",
            first_name="Admin",
            username="admin",
        )
        assert len(app.telegram.calls) == call_count_before_text

        updated_club = await _get_club(real_e2e_session_pool, club.id)
        assert updated_club.name == "Без изменений"

    run_async(scenario())
