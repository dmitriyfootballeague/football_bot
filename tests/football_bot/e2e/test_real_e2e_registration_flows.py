import pytest

from football_bot.keyboards.inline.registration_kb import PositionCallback
from football_bot.keyboards.inline.admin_kb import AdminRegAction
from football_bot.locales import messages as msg
from football_bot.models import PlayerRole, RegistrationStatus
from tests.football_bot.e2e.support import (
    _button_texts,
    _complete_registration_profile,
    _get_player_by_telegram_id,
    _start_registration,
    _submit_club_registration,
    _submit_free_agent_registration,
    _seed_tournament_and_club,
)

pytestmark = pytest.mark.e2e


def test_real_e2e_registration_free_agent_approval(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app

        await _submit_free_agent_registration(
            app,
            user_id=1001,
            first_name="Ivan",
            last_name="Petrov",
            username="ivan",
            position="forward",
            description=None,
            birth_date="01.02.2000",
            photo_file_id="photo-real-e2e",
        )

        player = await _get_player_by_telegram_id(real_e2e_session_pool, 1001)
        assert player is not None
        assert player.first_name == "Ivan"
        assert player.last_name == "Petrov"
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

        approved_player = await _get_player_by_telegram_id(real_e2e_session_pool, 1001)
        assert approved_player is not None
        assert approved_player.registration_status == RegistrationStatus.APPROVED

        approval_message = app.last_call(chat_id=1001, method="sendMessage")
        assert approval_message.payload["text"] == msg.NOTIF_REG_APPROVED.format(status="Свободный агент")
        assert _button_texts(approval_message) == ["Рейтинг за прошлый сезон", "Трансфер"]

    run_async(scenario())


def test_real_e2e_registration_club_rejection_and_reapply(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app
        tournament, club = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Высшая лига",
            club_name="Буревестник",
        )

        await _submit_club_registration(
            app,
            user_id=1401,
            first_name="Nikolay",
            last_name="Smirnov",
            username="nikolay_one",
            tournament_id=tournament.id,
            club_id=club.id,
            role="role_player",
            position="defender",
            description="Right back",
            birth_date="15.04.2001",
            photo_file_id="photo-club-reg",
        )

        player = await _get_player_by_telegram_id(real_e2e_session_pool, 1401)
        assert player is not None
        assert player.registration_status == RegistrationStatus.PENDING
        assert player.role == PlayerRole.PLAYER
        assert player.club_id == club.id
        original_player_id = player.id

        admin_notice = app.last_call(chat_id=9001, method="sendPhoto")
        await app.feed_callback_from_call(
            user_id=9001,
            data=AdminRegAction(action="reject", player_id=player.id).pack(),
            call=admin_notice,
            first_name="Admin",
            username="admin",
        )

        rejected_player = await _get_player_by_telegram_id(real_e2e_session_pool, 1401)
        assert rejected_player is not None
        assert rejected_player.registration_status == RegistrationStatus.REJECTED

        rejection_message = app.last_call(chat_id=1401, method="sendMessage")
        assert rejection_message.payload["text"] == msg.NOTIF_REG_REJECTED

        await app.feed_message(
            user_id=1401,
            text_value="/start",
            first_name="Nikolay",
            username="nikolay_one",
        )
        reapply_prompt = app.last_call(chat_id=1401, method="sendMessage")
        assert reapply_prompt.payload["text"] == msg.NOTIF_REG_REJECTED_REAPPLY

        await app.feed_callback_from_call(
            user_id=1401,
            data="registration",
            call=reapply_prompt,
            first_name="Ilya",
            username="ilya_two",
        )
        status_prompt = await _complete_registration_profile(
            app,
            user_id=1401,
            first_name="Ilya",
            last_name="Sokolov",
            username="ilya_two",
            position="forward",
            description=None,
            birth_date="21.09.2002",
            photo_file_id="photo-reapply",
        )
        await app.feed_callback_from_call(
            user_id=1401,
            data="status_free_agent",
            call=status_prompt,
            first_name="Ilya",
            username="ilya_two",
        )

        reapplied_player = await _get_player_by_telegram_id(real_e2e_session_pool, 1401)
        assert reapplied_player is not None
        assert reapplied_player.id == original_player_id
        assert reapplied_player.first_name == "Ilya"
        assert reapplied_player.last_name == "Sokolov"
        assert reapplied_player.registration_status == RegistrationStatus.PENDING
        assert reapplied_player.role == PlayerRole.FREE_AGENT
        assert reapplied_player.club_id is None

    run_async(scenario())


def test_real_e2e_registration_club_player_approval(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app
        tournament, club = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Дивизион А",
            club_name="Смена",
        )

        await _submit_club_registration(
            app,
            user_id=1411,
            first_name="Artem",
            last_name="Player",
            username="artem_player",
            tournament_id=tournament.id,
            club_id=club.id,
            role="role_player",
            position="forward",
            description=None,
            birth_date="03.03.2001",
            photo_file_id="photo-player-approval",
        )

        player = await _get_player_by_telegram_id(real_e2e_session_pool, 1411)
        assert player is not None
        assert player.role == PlayerRole.PLAYER
        assert player.registration_status == RegistrationStatus.PENDING

        admin_notice = app.last_call(chat_id=9001, method="sendPhoto")
        await app.feed_callback_from_call(
            user_id=9001,
            data=AdminRegAction(action="approve", player_id=player.id).pack(),
            call=admin_notice,
            first_name="Admin",
            username="admin",
        )

        approved_player = await _get_player_by_telegram_id(real_e2e_session_pool, 1411)
        assert approved_player is not None
        assert approved_player.registration_status == RegistrationStatus.APPROVED
        assert approved_player.role == PlayerRole.PLAYER

        approval_message = app.last_call(chat_id=1411, method="sendMessage")
        assert approval_message.payload["text"] == msg.NOTIF_REG_APPROVED.format(
            status=f"Игрок клуба: {club.name}"
        )
        assert _button_texts(approval_message) == ["Рейтинг", "Трансфер"]

    run_async(scenario())


def test_real_e2e_registration_club_captain_approval(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app
        tournament, club = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Дивизион B",
            club_name="Метеор",
        )

        await _submit_club_registration(
            app,
            user_id=1412,
            first_name="Sergey",
            last_name="Captain",
            username="sergey_captain",
            tournament_id=tournament.id,
            club_id=club.id,
            role="role_captain",
            position="defender",
            description="Leader",
            birth_date="05.05.1999",
            photo_file_id="photo-captain-approval",
        )

        captain = await _get_player_by_telegram_id(real_e2e_session_pool, 1412)
        assert captain is not None
        assert captain.role == PlayerRole.CAPTAIN
        assert captain.registration_status == RegistrationStatus.PENDING

        admin_notice = app.last_call(chat_id=9001, method="sendPhoto")
        await app.feed_callback_from_call(
            user_id=9001,
            data=AdminRegAction(action="approve", player_id=captain.id).pack(),
            call=admin_notice,
            first_name="Admin",
            username="admin",
        )

        approved_captain = await _get_player_by_telegram_id(real_e2e_session_pool, 1412)
        assert approved_captain is not None
        assert approved_captain.registration_status == RegistrationStatus.APPROVED
        assert approved_captain.role == PlayerRole.CAPTAIN

        approval_message = app.last_call(chat_id=1412, method="sendMessage")
        assert approval_message.payload["text"] == msg.NOTIF_REG_APPROVED.format(
            status=f"Игрок клуба: {club.name}"
        )
        assert _button_texts(approval_message) == ["Рейтинг", "Трансфер"]

    run_async(scenario())


def test_real_e2e_registration_validation_and_command_flows(run_async, real_e2e_app):
    async def scenario():
        app = real_e2e_app

        await app.feed_message(
            user_id=1420,
            text_value="/help",
            first_name="Helper",
            username="helper_user",
        )
        help_message = app.last_call(chat_id=1420, method="sendMessage")
        assert "Доступные команды" in help_message.payload["text"]

        await _start_registration(app, user_id=1420, first_name="Helper", username="helper_user")

        await app.feed_message(
            user_id=1420,
            text_value="123",
            first_name="Helper",
            username="helper_user",
        )
        assert app.last_call(chat_id=1420, method="sendMessage").payload["text"] == msg.ERR_INVALID_NAME

        await app.feed_message(
            user_id=1420,
            text_value="Helper",
            first_name="Helper",
            username="helper_user",
        )
        await app.feed_message(
            user_id=1420,
            text_value="456",
            first_name="Helper",
            username="helper_user",
        )
        assert app.last_call(chat_id=1420, method="sendMessage").payload["text"] == msg.ERR_INVALID_SURNAME

        await app.feed_message(
            user_id=1420,
            text_value="Tester",
            first_name="Helper",
            username="helper_user",
        )

        position_prompt = app.last_call(chat_id=1420, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1420,
            data=PositionCallback(position="forward").pack(),
            call=position_prompt,
            first_name="Helper",
            username="helper_user",
        )

        description_prompt = app.last_call(chat_id=1420, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1420,
            data="skip",
            call=description_prompt,
            first_name="Helper",
            username="helper_user",
        )

        await app.feed_message(
            user_id=1420,
            text_value="31-12-2000",
            first_name="Helper",
            username="helper_user",
        )
        assert app.last_call(chat_id=1420, method="sendMessage").payload["text"] == msg.ERR_INVALID_DATE

        await app.feed_message(
            user_id=1420,
            text_value="31.12.2000",
            first_name="Helper",
            username="helper_user",
        )
        await app.feed_message(
            user_id=1420,
            text_value="not a photo",
            first_name="Helper",
            username="helper_user",
        )
        assert app.last_call(chat_id=1420, method="sendMessage").payload["text"] == msg.ERR_INVALID_PHOTO

        await app.feed_message(
            user_id=1420,
            text_value="/cancel",
            first_name="Helper",
            username="helper_user",
        )
        cancel_message = app.last_call(chat_id=1420, method="sendMessage")
        assert cancel_message.payload["text"] == "Вы сбросили все действия и состояния."

        call_count = len(app.telegram.calls)
        await app.feed_message(
            user_id=1420,
            text_value="after cancel",
            first_name="Helper",
            username="helper_user",
        )
        assert len(app.telegram.calls) == call_count

    run_async(scenario())


def test_real_e2e_registration_pending_user_reopens_start(run_async, real_e2e_app):
    async def scenario():
        app = real_e2e_app

        await _submit_free_agent_registration(
            app,
            user_id=1421,
            first_name="Pending",
            last_name="User",
            username="pending_user",
            position="forward",
            description=None,
            birth_date="01.01.2001",
            photo_file_id="photo-pending",
        )

        await app.feed_message(
            user_id=1421,
            text_value="/start",
            first_name="Pending",
            username="pending_user",
        )
        pending_message = app.last_call(chat_id=1421, method="sendMessage")
        assert pending_message.payload["text"] == msg.NOTIF_REG_PENDING

    run_async(scenario())
