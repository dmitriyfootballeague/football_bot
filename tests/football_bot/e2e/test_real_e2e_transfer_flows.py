import pytest

from football_bot.keyboards.inline.registration_kb import ClubCallback, TournamentCallback
from football_bot.keyboards.inline.transfer_kb import (
    AdminTransferAction,
    KickPlayerCallback,
    TransferActionCallback,
    TransferDecisionCallback,
    TransferPlayerCallback,
)
from football_bot.locales import messages as msg
from football_bot.models import PlayerRole, RegistrationStatus, TransferStatus, TransferType
from tests.football_bot.e2e.support import (
    _get_player_by_telegram_id,
    _get_transfer_by_id,
    _get_transfer_for_player,
    _last_callback_answer,
    _seed_player,
    _seed_tournament_and_club,
    _seed_transfer_request,
)

pytestmark = pytest.mark.e2e


async def _open_transfer_menu(app, *, user_id: int, first_name: str, username: str):
    await app.feed_message(
        user_id=user_id,
        text_value="Трансфер",
        first_name=first_name,
        username=username,
    )
    return app.last_call(chat_id=user_id, method="sendMessage")


async def _submit_join_request(
    app,
    session_pool,
    *,
    user_id: int,
    first_name: str,
    username: str,
    tournament_id: int,
    club_id: int,
):
    transfer_menu = await _open_transfer_menu(
        app, user_id=user_id, first_name=first_name, username=username
    )
    await app.feed_callback_from_call(
        user_id=user_id,
        data=TransferActionCallback(action="join").pack(),
        call=transfer_menu,
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
    player = await _get_player_by_telegram_id(session_pool, user_id)
    assert player is not None
    return await _get_transfer_for_player(session_pool, player.id)


async def _submit_exit_request(app, session_pool, *, user_id: int, first_name: str, username: str):
    transfer_menu = await _open_transfer_menu(
        app, user_id=user_id, first_name=first_name, username=username
    )
    await app.feed_callback_from_call(
        user_id=user_id,
        data=TransferActionCallback(action="exit").pack(),
        call=transfer_menu,
        first_name=first_name,
        username=username,
    )
    player = await _get_player_by_telegram_id(session_pool, user_id)
    assert player is not None
    return await _get_transfer_for_player(session_pool, player.id)


async def _send_invite(app, session_pool, *, captain_id: int, captain_name: str, captain_username: str, player_id: int):
    transfer_menu = await _open_transfer_menu(
        app, user_id=captain_id, first_name=captain_name, username=captain_username
    )
    await app.feed_callback_from_call(
        user_id=captain_id,
        data=TransferActionCallback(action="free_agents").pack(),
        call=transfer_menu,
        first_name=captain_name,
        username=captain_username,
    )
    free_agent_profile = app.last_call(chat_id=captain_id, method="sendMessage")
    await app.feed_callback_from_call(
        user_id=captain_id,
        data=TransferPlayerCallback(player_id=player_id).pack(),
        call=free_agent_profile,
        first_name=captain_name,
        username=captain_username,
    )
    return free_agent_profile


async def _submit_kick_request(
    app,
    session_pool,
    *,
    captain_id: int,
    captain_name: str,
    captain_username: str,
    player_id: int,
):
    transfer_menu = await _open_transfer_menu(
        app, user_id=captain_id, first_name=captain_name, username=captain_username
    )
    await app.feed_callback_from_call(
        user_id=captain_id,
        data=TransferActionCallback(action="kick_player").pack(),
        call=transfer_menu,
        first_name=captain_name,
        username=captain_username,
    )
    kick_prompt = app.last_call(chat_id=captain_id, method="sendMessage")
    await app.feed_callback_from_call(
        user_id=captain_id,
        data=KickPlayerCallback(player_id=player_id).pack(),
        call=kick_prompt,
        first_name=captain_name,
        username=captain_username,
    )
    return await _get_transfer_for_player(session_pool, player_id)


def test_real_e2e_transfer_join_request_list_and_approval_flow(run_async, real_e2e_app, real_e2e_session_pool):
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

        request = await _submit_join_request(
            app,
            real_e2e_session_pool,
            user_id=1101,
            first_name="Pavel",
            username="pavel_free",
            tournament_id=tournament.id,
            club_id=club.id,
        )
        assert request.status == TransferStatus.PENDING_CAPTAIN
        assert request.to_club_id == club.id

        captain_menu = await _open_transfer_menu(
            app, user_id=1102, first_name="Captain", username="captain_club"
        )
        await app.feed_callback_from_call(
            user_id=1102,
            data=TransferActionCallback(action="join_requests").pack(),
            call=captain_menu,
            first_name="Captain",
            username="captain_club",
        )
        join_request_message = app.last_call(chat_id=1102, method="sendMessage")
        assert msg.TRANSFER_JOIN_CAPTAIN_NOTIF.format(name="Pavel Free") in join_request_message.payload["text"]

        await app.feed_callback_from_call(
            user_id=1102,
            data=TransferDecisionCallback(request_id=request.id, action="approve").pack(),
            call=join_request_message,
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


def test_real_e2e_transfer_exit_request_list_and_approval_flow(run_async, real_e2e_app, real_e2e_session_pool):
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

        request = await _submit_exit_request(
            app,
            real_e2e_session_pool,
            user_id=1201,
            first_name="Roman",
            username="roman_leave",
        )
        assert request.status == TransferStatus.PENDING_CAPTAIN

        captain_menu = await _open_transfer_menu(
            app, user_id=1202, first_name="Captain", username="captain_elite"
        )
        await app.feed_callback_from_call(
            user_id=1202,
            data=TransferActionCallback(action="exit_requests").pack(),
            call=captain_menu,
            first_name="Captain",
            username="captain_elite",
        )
        exit_request_message = app.last_call(chat_id=1202, method="sendMessage")
        assert exit_request_message.payload["text"] == msg.TRANSFER_EXIT_CAPTAIN_NOTIF.format(
            name="Roman Leave"
        )

        await app.feed_callback_from_call(
            user_id=1202,
            data=TransferDecisionCallback(request_id=request.id, action="approve").pack(),
            call=exit_request_message,
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


def test_real_e2e_transfer_invite_rejection_flow(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app
        _, club = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Первая лига",
            club_name="Феникс",
        )
        await _seed_player(
            real_e2e_session_pool,
            telegram_id=1251,
            first_name="Captain",
            last_name="Phoenix",
            username="captain_phoenix",
            role=PlayerRole.CAPTAIN,
            registration_status=RegistrationStatus.APPROVED,
            club_id=club.id,
            current_rating=8.9,
        )
        free_agent = await _seed_player(
            real_e2e_session_pool,
            telegram_id=1252,
            first_name="Anton",
            last_name="Free",
            username="anton_free",
            role=PlayerRole.FREE_AGENT,
            registration_status=RegistrationStatus.APPROVED,
            club_id=None,
            prev_season_rating=7.4,
        )

        await _send_invite(
            app,
            real_e2e_session_pool,
            captain_id=1251,
            captain_name="Captain",
            captain_username="captain_phoenix",
            player_id=free_agent.id,
        )

        request = await _get_transfer_for_player(real_e2e_session_pool, free_agent.id)
        assert request.status == TransferStatus.PENDING_PLAYER_CONFIRM

        fa_transfer_menu = await _open_transfer_menu(
            app, user_id=1252, first_name="Anton", username="anton_free"
        )
        await app.feed_callback_from_call(
            user_id=1252,
            data=TransferActionCallback(action="invitations").pack(),
            call=fa_transfer_menu,
            first_name="Anton",
            username="anton_free",
        )

        invitation_notice = app.last_call(chat_id=1252, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1252,
            data=TransferDecisionCallback(request_id=request.id, action="reject").pack(),
            call=invitation_notice,
            first_name="Anton",
            username="anton_free",
        )

        rejected_request = await _get_transfer_for_player(real_e2e_session_pool, free_agent.id)
        assert rejected_request.status == TransferStatus.REJECTED

        captain_notice = app.last_call(chat_id=1251, method="sendMessage")
        assert captain_notice.payload["text"] == msg.TRANSFER_INVITE_PLAYER_REJECTED.format(
            name="Anton Free"
        )

    run_async(scenario())


def test_real_e2e_transfer_admin_reject_exit_flow(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app
        _, club = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Отказ выход",
            club_name="Волна",
        )
        captain = await _seed_player(
            real_e2e_session_pool,
            telegram_id=1602,
            first_name="Captain",
            last_name="Wave",
            username="captain_wave",
            role=PlayerRole.CAPTAIN,
            registration_status=RegistrationStatus.APPROVED,
            club_id=club.id,
        )
        player = await _seed_player(
            real_e2e_session_pool,
            telegram_id=1601,
            first_name="Exit",
            last_name="Target",
            username="exit_target",
            role=PlayerRole.PLAYER,
            registration_status=RegistrationStatus.APPROVED,
            club_id=club.id,
        )

        request = await _submit_exit_request(
            app,
            real_e2e_session_pool,
            user_id=1601,
            first_name="Exit",
            username="exit_target",
        )
        captain_notice = app.last_call(chat_id=1602, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1602,
            data=TransferDecisionCallback(request_id=request.id, action="approve").pack(),
            call=captain_notice,
            first_name="Captain",
            username="captain_wave",
        )

        admin_notice = app.last_call(chat_id=9001, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=9001,
            data=AdminTransferAction(action="reject", request_id=request.id).pack(),
            call=admin_notice,
            first_name="Admin",
            username="admin",
        )

        rejected_request = await _get_transfer_by_id(real_e2e_session_pool, request.id)
        assert rejected_request.status == TransferStatus.REJECTED
        player_message = app.last_call(chat_id=1601, method="sendMessage")
        assert player_message.payload["text"] == msg.TRANSFER_EXIT_ADMIN_REJECTED
        captain_message = app.last_call(chat_id=1602, method="sendMessage")
        assert captain_message.payload["text"] == msg.TRANSFER_EXIT_ADMIN_REJECTED_CAPTAIN.format(
            name="Exit Target"
        )

    run_async(scenario())


def test_real_e2e_transfer_admin_reject_join_flow(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app
        tournament, club = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Отказ вход",
            club_name="Спутник",
        )
        await _seed_player(
            real_e2e_session_pool,
            telegram_id=1612,
            first_name="Captain",
            last_name="Join",
            username="captain_join",
            role=PlayerRole.CAPTAIN,
            registration_status=RegistrationStatus.APPROVED,
            club_id=club.id,
        )
        player = await _seed_player(
            real_e2e_session_pool,
            telegram_id=1611,
            first_name="Join",
            last_name="Target",
            username="join_target",
            role=PlayerRole.FREE_AGENT,
            registration_status=RegistrationStatus.APPROVED,
            club_id=None,
        )

        request = await _submit_join_request(
            app,
            real_e2e_session_pool,
            user_id=1611,
            first_name="Join",
            username="join_target",
            tournament_id=tournament.id,
            club_id=club.id,
        )
        captain_notice = app.last_call(chat_id=1612, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1612,
            data=TransferDecisionCallback(request_id=request.id, action="approve").pack(),
            call=captain_notice,
            first_name="Captain",
            username="captain_join",
        )

        confirm_notice = app.last_call(chat_id=1611, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1611,
            data=TransferDecisionCallback(request_id=request.id, action="confirm").pack(),
            call=confirm_notice,
            first_name="Join",
            username="join_target",
        )

        admin_notice = app.last_call(chat_id=9001, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=9001,
            data=AdminTransferAction(action="reject", request_id=request.id).pack(),
            call=admin_notice,
            first_name="Admin",
            username="admin",
        )

        rejected_request = await _get_transfer_by_id(real_e2e_session_pool, request.id)
        assert rejected_request.status == TransferStatus.REJECTED
        player_message = app.last_call(chat_id=1611, method="sendMessage")
        assert player_message.payload["text"] == msg.TRANSFER_JOIN_ADMIN_REJECTED.format(club=club.name)
        captain_message = app.last_call(chat_id=1612, method="sendMessage")
        assert captain_message.payload["text"] == msg.TRANSFER_JOIN_ADMIN_REJECTED_CAPTAIN.format(
            name="Join Target"
        )
        updated_player = await _get_player_by_telegram_id(real_e2e_session_pool, 1611)
        assert updated_player is not None
        assert updated_player.club_id is None
        assert updated_player.role == PlayerRole.FREE_AGENT

    run_async(scenario())


def test_real_e2e_transfer_admin_reject_invite_flow(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app
        _, club = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Отказ инвайт",
            club_name="Сокол",
        )
        await _seed_player(
            real_e2e_session_pool,
            telegram_id=1621,
            first_name="Captain",
            last_name="Invite",
            username="captain_invite",
            role=PlayerRole.CAPTAIN,
            registration_status=RegistrationStatus.APPROVED,
            club_id=club.id,
        )
        free_agent = await _seed_player(
            real_e2e_session_pool,
            telegram_id=1622,
            first_name="Invite",
            last_name="Target",
            username="invite_target",
            role=PlayerRole.FREE_AGENT,
            registration_status=RegistrationStatus.APPROVED,
            club_id=None,
        )

        await _send_invite(
            app,
            real_e2e_session_pool,
            captain_id=1621,
            captain_name="Captain",
            captain_username="captain_invite",
            player_id=free_agent.id,
        )
        request = await _get_transfer_for_player(real_e2e_session_pool, free_agent.id)

        fa_menu = await _open_transfer_menu(
            app, user_id=1622, first_name="Invite", username="invite_target"
        )
        await app.feed_callback_from_call(
            user_id=1622,
            data=TransferActionCallback(action="invitations").pack(),
            call=fa_menu,
            first_name="Invite",
            username="invite_target",
        )
        invitation_notice = app.last_call(chat_id=1622, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1622,
            data=TransferDecisionCallback(request_id=request.id, action="approve").pack(),
            call=invitation_notice,
            first_name="Invite",
            username="invite_target",
        )

        captain_menu = await _open_transfer_menu(
            app, user_id=1621, first_name="Captain", username="captain_invite"
        )
        await app.feed_callback_from_call(
            user_id=1621,
            data=TransferActionCallback(action="join_requests").pack(),
            call=captain_menu,
            first_name="Captain",
            username="captain_invite",
        )
        confirm_notice = app.last_call(chat_id=1621, method="sendMessage")
        assert msg.TRANSFER_INVITE_PLAYER_ACCEPTED_CAPTAIN.format(name="Invite Target") in confirm_notice.payload["text"]
        await app.feed_callback_from_call(
            user_id=1621,
            data=TransferDecisionCallback(request_id=request.id, action="confirm").pack(),
            call=confirm_notice,
            first_name="Captain",
            username="captain_invite",
        )

        admin_notice = app.last_call(chat_id=9001, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=9001,
            data=AdminTransferAction(action="reject", request_id=request.id).pack(),
            call=admin_notice,
            first_name="Admin",
            username="admin",
        )

        rejected_request = await _get_transfer_by_id(real_e2e_session_pool, request.id)
        assert rejected_request.status == TransferStatus.REJECTED
        player_message = app.last_call(chat_id=1622, method="sendMessage")
        assert player_message.payload["text"] == msg.TRANSFER_INVITE_ADMIN_REJECTED.format(club=club.name)
        captain_message = app.last_call(chat_id=1621, method="sendMessage")
        assert captain_message.payload["text"] == msg.TRANSFER_INVITE_ADMIN_REJECTED_CAPTAIN.format(
            name="Invite Target"
        )

    run_async(scenario())


def test_real_e2e_transfer_kick_approve_flow(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app
        _, club = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Кик апрув",
            club_name="Торпедо",
        )
        await _seed_player(
            real_e2e_session_pool,
            telegram_id=1631,
            first_name="Captain",
            last_name="Kick",
            username="captain_kick",
            role=PlayerRole.CAPTAIN,
            registration_status=RegistrationStatus.APPROVED,
            club_id=club.id,
        )
        player = await _seed_player(
            real_e2e_session_pool,
            telegram_id=1632,
            first_name="Kick",
            last_name="Player",
            username="kick_player",
            role=PlayerRole.PLAYER,
            registration_status=RegistrationStatus.APPROVED,
            club_id=club.id,
        )

        request = await _submit_kick_request(
            app,
            real_e2e_session_pool,
            captain_id=1631,
            captain_name="Captain",
            captain_username="captain_kick",
            player_id=player.id,
        )
        assert request.status == TransferStatus.PENDING_ADMIN

        admin_notice = app.last_call(chat_id=9001, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=9001,
            data=AdminTransferAction(action="approve", request_id=request.id).pack(),
            call=admin_notice,
            first_name="Admin",
            username="admin",
        )

        updated_player = await _get_player_by_telegram_id(real_e2e_session_pool, 1632)
        assert updated_player is not None
        assert updated_player.club_id is None
        assert updated_player.role == PlayerRole.FREE_AGENT

    run_async(scenario())


def test_real_e2e_transfer_admin_reject_kick_flow(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app
        _, club = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Кик реджект",
            club_name="Ротор",
        )
        await _seed_player(
            real_e2e_session_pool,
            telegram_id=1641,
            first_name="Captain",
            last_name="Rotor",
            username="captain_rotor",
            role=PlayerRole.CAPTAIN,
            registration_status=RegistrationStatus.APPROVED,
            club_id=club.id,
        )
        player = await _seed_player(
            real_e2e_session_pool,
            telegram_id=1642,
            first_name="Reject",
            last_name="Kick",
            username="reject_kick",
            role=PlayerRole.PLAYER,
            registration_status=RegistrationStatus.APPROVED,
            club_id=club.id,
        )

        request = await _submit_kick_request(
            app,
            real_e2e_session_pool,
            captain_id=1641,
            captain_name="Captain",
            captain_username="captain_rotor",
            player_id=player.id,
        )

        admin_notice = app.last_call(chat_id=9001, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=9001,
            data=AdminTransferAction(action="reject", request_id=request.id).pack(),
            call=admin_notice,
            first_name="Admin",
            username="admin",
        )

        rejected_request = await _get_transfer_by_id(real_e2e_session_pool, request.id)
        assert rejected_request.status == TransferStatus.REJECTED
        player_message = app.last_call(chat_id=1642, method="sendMessage")
        assert player_message.payload["text"] == msg.TRANSFER_KICK_ADMIN_REJECTED
        captain_message = app.last_call(chat_id=1641, method="sendMessage")
        assert captain_message.payload["text"] == msg.TRANSFER_KICK_ADMIN_REJECTED_CAPTAIN.format(
            name="Reject Kick"
        )

    run_async(scenario())


def test_real_e2e_transfer_edge_cases_active_request_and_same_club(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app
        tournament, club = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Эдж кейсы",
            club_name="Локомотив",
        )
        active_player = await _seed_player(
            real_e2e_session_pool,
            telegram_id=1701,
            first_name="Active",
            last_name="Player",
            username="active_player",
            role=PlayerRole.FREE_AGENT,
            registration_status=RegistrationStatus.APPROVED,
            club_id=None,
        )
        own_club_player = await _seed_player(
            real_e2e_session_pool,
            telegram_id=1702,
            first_name="Own",
            last_name="Club",
            username="own_club",
            role=PlayerRole.PLAYER,
            registration_status=RegistrationStatus.APPROVED,
            club_id=club.id,
        )
        await _seed_player(
            real_e2e_session_pool,
            telegram_id=1703,
            first_name="Captain",
            last_name="Edge",
            username="captain_edge",
            role=PlayerRole.CAPTAIN,
            registration_status=RegistrationStatus.APPROVED,
            club_id=club.id,
        )

        await _seed_transfer_request(
            real_e2e_session_pool,
            player_id=active_player.id,
            transfer_type=TransferType.JOIN,
            status=TransferStatus.PENDING_CAPTAIN,
            initiated_by=active_player.telegram_id,
            to_club_id=club.id,
        )

        active_menu = await _open_transfer_menu(
            app, user_id=1701, first_name="Active", username="active_player"
        )
        await app.feed_callback_from_call(
            user_id=1701,
            data=TransferActionCallback(action="join").pack(),
            call=active_menu,
            first_name="Active",
            username="active_player",
        )
        active_alert = _last_callback_answer(app)
        assert active_alert.payload["text"] == msg.TRANSFER_ACTIVE_EXISTS
        assert active_alert.payload["show_alert"] is True

        own_menu = await _open_transfer_menu(
            app, user_id=1702, first_name="Own", username="own_club"
        )
        await app.feed_callback_from_call(
            user_id=1702,
            data=TransferActionCallback(action="join").pack(),
            call=own_menu,
            first_name="Own",
            username="own_club",
        )
        tournament_prompt = app.last_call(chat_id=1702, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1702,
            data=TournamentCallback(tournament_id=tournament.id).pack(),
            call=tournament_prompt,
            first_name="Own",
            username="own_club",
        )
        club_prompt = app.last_call(chat_id=1702, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1702,
            data=ClubCallback(club_id=club.id).pack(),
            call=club_prompt,
            first_name="Own",
            username="own_club",
        )
        same_club_alert = _last_callback_answer(app)
        assert same_club_alert.payload["text"] == msg.TRANSFER_SAME_CLUB
        assert same_club_alert.payload["show_alert"] is True

    run_async(scenario())


def test_real_e2e_transfer_edge_cases_missing_captain(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app
        tournament, club_without_captain = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Без капитана",
            club_name="Без лидера",
        )
        _, player_club = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Команда игрока",
            club_name="Игроки",
        )
        player = await _seed_player(
            real_e2e_session_pool,
            telegram_id=1711,
            first_name="No",
            last_name="Captain",
            username="no_captain_player",
            role=PlayerRole.PLAYER,
            registration_status=RegistrationStatus.APPROVED,
            club_id=player_club.id,
        )
        free_agent = await _seed_player(
            real_e2e_session_pool,
            telegram_id=1712,
            first_name="No",
            last_name="Leader",
            username="no_leader_fa",
            role=PlayerRole.FREE_AGENT,
            registration_status=RegistrationStatus.APPROVED,
            club_id=None,
        )

        exit_menu = await _open_transfer_menu(
            app, user_id=1711, first_name="No", username="no_captain_player"
        )
        await app.feed_callback_from_call(
            user_id=1711,
            data=TransferActionCallback(action="exit").pack(),
            call=exit_menu,
            first_name="No",
            username="no_captain_player",
        )
        exit_alert = _last_callback_answer(app)
        assert exit_alert.payload["text"] == msg.TRANSFER_NO_CAPTAIN
        assert exit_alert.payload["show_alert"] is True

        join_menu = await _open_transfer_menu(
            app, user_id=1712, first_name="No", username="no_leader_fa"
        )
        await app.feed_callback_from_call(
            user_id=1712,
            data=TransferActionCallback(action="join").pack(),
            call=join_menu,
            first_name="No",
            username="no_leader_fa",
        )
        tournament_prompt = app.last_call(chat_id=1712, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1712,
            data=TournamentCallback(tournament_id=tournament.id).pack(),
            call=tournament_prompt,
            first_name="No",
            username="no_leader_fa",
        )
        club_prompt = app.last_call(chat_id=1712, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1712,
            data=ClubCallback(club_id=club_without_captain.id).pack(),
            call=club_prompt,
            first_name="No",
            username="no_leader_fa",
        )
        join_notice = app.last_call(chat_id=1712, method="sendMessage")
        assert join_notice.payload["text"] == msg.TRANSFER_NO_CAPTAIN

    run_async(scenario())


def test_real_e2e_transfer_kick_player_not_in_club_edge_case(run_async, real_e2e_app, real_e2e_session_pool):
    async def scenario():
        app = real_e2e_app
        _, captain_club = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Кик эдж",
            club_name="Заря",
        )
        _, other_club = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Другой клуб",
            club_name="Орбита",
        )
        await _seed_player(
            real_e2e_session_pool,
            telegram_id=1721,
            first_name="Captain",
            last_name="Zarya",
            username="captain_zarya",
            role=PlayerRole.CAPTAIN,
            registration_status=RegistrationStatus.APPROVED,
            club_id=captain_club.id,
        )
        outsider = await _seed_player(
            real_e2e_session_pool,
            telegram_id=1722,
            first_name="Out",
            last_name="Side",
            username="outside_player",
            role=PlayerRole.PLAYER,
            registration_status=RegistrationStatus.APPROVED,
            club_id=other_club.id,
        )

        captain_menu = await _open_transfer_menu(
            app, user_id=1721, first_name="Captain", username="captain_zarya"
        )
        await app.feed_callback_from_call(
            user_id=1721,
            data=TransferActionCallback(action="kick_player").pack(),
            call=captain_menu,
            first_name="Captain",
            username="captain_zarya",
        )
        kick_prompt = app.last_call(chat_id=1721, method="sendMessage")
        await app.feed_callback_from_call(
            user_id=1721,
            data=KickPlayerCallback(player_id=outsider.id).pack(),
            call=kick_prompt,
            first_name="Captain",
            username="captain_zarya",
        )
        kick_alert = _last_callback_answer(app)
        assert kick_alert.payload["text"] == msg.TRANSFER_PLAYER_NOT_IN_CLUB
        assert kick_alert.payload["show_alert"] is True

    run_async(scenario())
