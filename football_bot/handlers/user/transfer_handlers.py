from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from football_bot.keyboards.inline.registration_kb import (
    create_tournament_kb, create_club_kb, TournamentCallback, ClubCallback,
)
from football_bot.keyboards.inline.transfer_kb import (
    TransferActionCallback, TransferDecisionCallback, TransferPlayerCallback,
    KickPlayerCallback,
    create_player_transfer_menu, create_free_agent_transfer_menu,
    create_captain_transfer_menu, create_transfer_decision_kb,
    create_transfer_confirm_kb,
    create_invite_kb, create_admin_transfer_kb, create_kick_players_kb,
)
from football_bot.keyboards.reply.main_menu import create_free_agent_menu, create_player_menu
from football_bot.locales import messages as msg
from football_bot.models import Player, PlayerPosition, PlayerRole
from football_bot.repository import PlayerRepository, TournamentRepository, ClubRepository
from football_bot.service import TransferService
from football_bot.states import FSMTransfer

router = Router()

POSITION_LABELS = {
    PlayerPosition.GOALKEEPER: "Вратарь",
    PlayerPosition.DEFENDER: "Защитник",
    PlayerPosition.MIDFIELDER: "Полузащитник",
    PlayerPosition.FORWARD: "Нападающий",
}


# ========== ENTRY POINT: "Трансфер" reply button ==========

@router.message(F.text == "Трансфер")
async def transfer_menu(message: Message, session: AsyncSession):
    repo = PlayerRepository(session)
    player = await repo.get_by_telegram_id(message.from_user.id)
    if not player:
        return

    if player.role == PlayerRole.CAPTAIN:
        await message.answer(msg.TRANSFER_MENU, reply_markup=create_captain_transfer_menu())
    elif player.role == PlayerRole.FREE_AGENT:
        await message.answer(msg.TRANSFER_MENU, reply_markup=create_free_agent_transfer_menu())
    else:
        await message.answer(msg.TRANSFER_MENU, reply_markup=create_player_transfer_menu())


# ========== PLAYER: EXIT CLUB ==========

@router.callback_query(TransferActionCallback.filter(F.action == "exit"))
async def player_exit_club(callback: CallbackQuery, session: AsyncSession):
    repo = PlayerRepository(session)
    player = await repo.get_by_telegram_id(callback.from_user.id)
    if not player or not player.club_id:
        await callback.answer(msg.TRANSFER_NO_CLUB, show_alert=True)
        return

    svc = TransferService(session)
    active = await svc.get_active_for_player(player.id)
    if active:
        await callback.answer(msg.TRANSFER_ACTIVE_EXISTS, show_alert=True)
        return

    captain = await svc.get_captain_of_club(player.club_id)
    if not captain:
        await callback.answer(msg.TRANSFER_NO_CAPTAIN, show_alert=True)
        return

    request = await svc.create_exit_request(player)
    await callback.message.answer(msg.TRANSFER_EXIT_SENT)

    # Notify captain
    try:
        name = f"{player.first_name} {player.last_name}"
        await callback.bot.send_message(
            chat_id=captain.telegram_id,
            text=msg.TRANSFER_EXIT_CAPTAIN_NOTIF.format(name=name),
            reply_markup=create_transfer_decision_kb(request.id),
        )
    except Exception:
        pass

    await callback.answer()


# ========== PLAYER/FA: JOIN CLUB (FSM) ==========

@router.callback_query(TransferActionCallback.filter(F.action == "join"))
async def start_join_flow(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    repo = PlayerRepository(session)
    player = await repo.get_by_telegram_id(callback.from_user.id)
    if not player:
        await callback.answer()
        return

    svc = TransferService(session)
    active = await svc.get_active_for_player(player.id)
    if active:
        await callback.answer(msg.TRANSFER_ACTIVE_EXISTS, show_alert=True)
        return

    tourn_repo = TournamentRepository(session)
    tournaments = await tourn_repo.get_all()
    if not tournaments:
        await callback.message.answer("Турниры ещё не загружены. Попробуйте позже.")
        await callback.answer()
        return

    await callback.message.answer(msg.REG_CHOOSE_TOURNAMENT, reply_markup=create_tournament_kb(tournaments))
    await state.set_state(FSMTransfer.choose_tournament)
    await callback.answer()


@router.callback_query(TournamentCallback.filter(), StateFilter(FSMTransfer.choose_tournament))
async def transfer_choose_tournament(
    callback: CallbackQuery, callback_data: TournamentCallback,
    state: FSMContext, session: AsyncSession,
):
    await state.update_data(tournament_id=callback_data.tournament_id)
    club_repo = ClubRepository(session)
    clubs = await club_repo.get_by_tournament_id(callback_data.tournament_id)
    if not clubs:
        await callback.message.answer("В этом турнире пока нет клубов.")
        await callback.answer()
        return
    await callback.message.answer(msg.REG_CHOOSE_CLUB, reply_markup=create_club_kb(clubs))
    await state.set_state(FSMTransfer.choose_club)
    await callback.answer()


@router.callback_query(ClubCallback.filter(), StateFilter(FSMTransfer.choose_club))
async def transfer_choose_club(
    callback: CallbackQuery, callback_data: ClubCallback,
    state: FSMContext, session: AsyncSession,
):
    await state.clear()
    to_club_id = callback_data.club_id

    repo = PlayerRepository(session)
    player = await repo.get_by_telegram_id(callback.from_user.id)
    if not player:
        await callback.answer()
        return

    if player.club_id == to_club_id:
        await callback.answer(msg.TRANSFER_SAME_CLUB, show_alert=True)
        return

    svc = TransferService(session)
    captain = await svc.get_captain_of_club(to_club_id)
    if not captain:
        await callback.message.answer(msg.TRANSFER_NO_CAPTAIN)
        await callback.answer()
        return

    club_repo = ClubRepository(session)
    club = await club_repo.get_by_id(to_club_id)
    club_name = club.name if club else "—"

    request = await svc.create_join_request(player, to_club_id)
    await callback.message.answer(msg.TRANSFER_JOIN_SENT.format(club=club_name))

    # Notify captain of target club
    try:
        name = f"{player.first_name} {player.last_name}"
        await callback.bot.send_message(
            chat_id=captain.telegram_id,
            text=msg.TRANSFER_JOIN_CAPTAIN_NOTIF.format(name=name),
            reply_markup=create_transfer_decision_kb(request.id),
        )
    except Exception:
        pass

    await callback.answer()


# ========== FA: VIEW INVITATIONS ==========

@router.callback_query(TransferActionCallback.filter(F.action == "invitations"))
async def fa_view_invitations(callback: CallbackQuery, session: AsyncSession):
    repo = PlayerRepository(session)
    player = await repo.get_by_telegram_id(callback.from_user.id)
    if not player:
        await callback.answer()
        return

    svc = TransferService(session)
    invitations = await svc.get_invitations_for_player(player.id)
    if not invitations:
        await callback.message.answer(msg.TRANSFER_NO_INVITATIONS)
        await callback.answer()
        return

    for inv in invitations:
        club_name = inv.to_club.name if inv.to_club else "—"
        await callback.message.answer(
            msg.TRANSFER_INVITE_PLAYER_NOTIF.format(club=club_name),
            reply_markup=create_transfer_decision_kb(inv.id),
        )
    await callback.answer()


# ========== CAPTAIN: FREE AGENTS LIST ==========

@router.callback_query(TransferActionCallback.filter(F.action == "free_agents"))
async def captain_view_free_agents(callback: CallbackQuery, session: AsyncSession):
    repo = PlayerRepository(session)
    captain = await repo.get_by_telegram_id(callback.from_user.id)
    if not captain or captain.role != PlayerRole.CAPTAIN or not captain.club_id:
        await callback.answer(msg.TRANSFER_ACTION_FORBIDDEN, show_alert=True)
        return

    svc = TransferService(session)
    free_agents = await svc.get_free_agents()
    if not free_agents:
        await callback.message.answer(msg.TRANSFER_NO_FREE_AGENTS)
        await callback.answer()
        return

    for fa in free_agents:
        text = _render_player_profile(fa)
        await callback.message.answer(text, reply_markup=create_invite_kb(fa.id))
    await callback.answer()


# ========== CAPTAIN: INVITE FA ==========

@router.callback_query(TransferPlayerCallback.filter())
async def captain_invite_fa(
    callback: CallbackQuery, callback_data: TransferPlayerCallback, session: AsyncSession,
):
    repo = PlayerRepository(session)
    captain = await repo.get_by_telegram_id(callback.from_user.id)
    if not captain or captain.role != PlayerRole.CAPTAIN or not captain.club_id:
        await callback.answer()
        return

    svc = TransferService(session)
    target = await repo.get_by_id(callback_data.player_id)
    if not target:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    if target.role != PlayerRole.FREE_AGENT:
        await callback.answer(msg.TRANSFER_ACTION_FORBIDDEN, show_alert=True)
        return

    # Check if target already has active transfer
    active = await svc.get_active_for_player(target.id)
    if active:
        await callback.answer(msg.TRANSFER_ACTIVE_EXISTS, show_alert=True)
        return

    club_repo = ClubRepository(session)
    club = await club_repo.get_by_id(captain.club_id)
    club_name = club.name if club else "—"

    request = await svc.create_invite(captain, target.id, captain.club_id)
    name = f"{target.first_name} {target.last_name}"
    await callback.message.answer(msg.TRANSFER_INVITE_SENT.format(name=name))

    # Notify FA about invitation
    try:
        await callback.bot.send_message(
            chat_id=target.telegram_id,
            text=msg.TRANSFER_INVITE_PLAYER_NOTIF.format(club=club_name),
            reply_markup=create_transfer_decision_kb(request.id),
        )
    except Exception:
        pass

    await callback.answer()


# ========== CAPTAIN: JOIN REQUESTS ==========

@router.callback_query(TransferActionCallback.filter(F.action == "join_requests"))
async def captain_view_join_requests(callback: CallbackQuery, session: AsyncSession):
    repo = PlayerRepository(session)
    captain = await repo.get_by_telegram_id(callback.from_user.id)
    if not captain or captain.role != PlayerRole.CAPTAIN or not captain.club_id:
        await callback.answer(msg.TRANSFER_ACTION_FORBIDDEN, show_alert=True)
        return

    svc = TransferService(session)
    requests = await svc.get_join_requests_for_captain(captain.club_id)

    # Also include invite confirms (FA accepted, captain needs to confirm)
    invite_confirms = await svc.get_invite_confirms_for_captain(captain.club_id)
    requests.extend(invite_confirms)

    if not requests:
        await callback.message.answer(msg.TRANSFER_NO_JOIN_REQUESTS)
        await callback.answer()
        return

    for req in requests:
        name = f"{req.player.first_name} {req.player.last_name}"
        if req.transfer_type.value == "invite":
            # Captain needs to confirm after FA accepted
            await callback.message.answer(
                f"{_render_player_profile(req.player)}\n\n"
                f"{msg.TRANSFER_INVITE_PLAYER_ACCEPTED_CAPTAIN.format(name=name)}",
                reply_markup=create_transfer_confirm_kb(req.id),
            )
        else:
            await callback.message.answer(
                f"{_render_player_profile(req.player)}\n\n"
                f"{msg.TRANSFER_JOIN_CAPTAIN_NOTIF.format(name=name)}",
                reply_markup=create_transfer_decision_kb(req.id),
            )
    await callback.answer()


# ========== CAPTAIN: EXIT REQUESTS ==========

@router.callback_query(TransferActionCallback.filter(F.action == "exit_requests"))
async def captain_view_exit_requests(callback: CallbackQuery, session: AsyncSession):
    repo = PlayerRepository(session)
    captain = await repo.get_by_telegram_id(callback.from_user.id)
    if not captain or captain.role != PlayerRole.CAPTAIN or not captain.club_id:
        await callback.answer(msg.TRANSFER_ACTION_FORBIDDEN, show_alert=True)
        return

    svc = TransferService(session)
    requests = await svc.get_exit_requests_for_captain(captain.club_id)
    if not requests:
        await callback.message.answer(msg.TRANSFER_NO_EXIT_REQUESTS)
        await callback.answer()
        return

    for req in requests:
        name = f"{req.player.first_name} {req.player.last_name}"
        await callback.message.answer(
            msg.TRANSFER_EXIT_CAPTAIN_NOTIF.format(name=name),
            reply_markup=create_transfer_decision_kb(req.id),
        )
    await callback.answer()


# ========== DECISION CALLBACKS (shared for captain & player) ==========

@router.callback_query(TransferDecisionCallback.filter(F.action == "approve"))
async def decision_approve(
    callback: CallbackQuery, callback_data: TransferDecisionCallback,
    session: AsyncSession, admin_ids: list, league_admin_ids: list,
):
    svc = TransferService(session)
    req = await svc.get_request(callback_data.request_id)
    if not req:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    repo = PlayerRepository(session)
    actor = await repo.get_by_telegram_id(callback.from_user.id)
    if not actor:
        await callback.answer()
        return

    player = req.player
    name = f"{player.first_name} {player.last_name}"

    # Determine who is approving based on role and request state
    if actor.role == PlayerRole.CAPTAIN:
        if not _captain_can_manage_request(actor, req):
            await callback.answer(msg.TRANSFER_ACTION_FORBIDDEN, show_alert=True)
            return

        # Captain approving EXIT or JOIN
        req = await svc.captain_approve(callback_data.request_id)

        if req.transfer_type.value == "exit":
            # EXIT → now pending admin
            await callback.message.edit_text(f"✅ Вы одобрили выход {name}")
            try:
                await callback.bot.send_message(
                    chat_id=player.telegram_id,
                    text=msg.TRANSFER_EXIT_CAPTAIN_APPROVED,
                )
            except Exception:
                pass
            # Notify admin
            await _notify_admins_transfer(
                callback.bot, admin_ids, league_admin_ids, req, svc, session,
            )

        elif req.transfer_type.value == "join":
            # JOIN → now pending player confirmation
            club_repo = ClubRepository(session)
            club = await club_repo.get_by_id(req.to_club_id)
            club_name = club.name if club else "—"
            await callback.message.edit_text(f"✅ Вы одобрили трансфер {name}")
            try:
                await callback.bot.send_message(
                    chat_id=player.telegram_id,
                    text=msg.TRANSFER_JOIN_CAPTAIN_APPROVED.format(club=club_name),
                    reply_markup=create_transfer_confirm_kb(req.id),
                )
            except Exception:
                pass

    elif actor.role == PlayerRole.FREE_AGENT:
        if req.transfer_type.value != "invite" or actor.id != player.id:
            await callback.answer(msg.TRANSFER_ACTION_FORBIDDEN, show_alert=True)
            return

        # FA accepting invitation
        req = await svc.player_accept_invite(callback_data.request_id)
        club_name = req.to_club.name if req.to_club else "—"
        await callback.message.edit_text(f"✅ Вы приняли приглашение от клуба {club_name}")

        # Notify captain for final confirmation
        captain = await svc.get_captain_of_club(req.to_club_id)
        if captain:
            try:
                await callback.bot.send_message(
                    chat_id=captain.telegram_id,
                    text=msg.TRANSFER_INVITE_PLAYER_ACCEPTED_CAPTAIN.format(name=name),
                    reply_markup=create_transfer_confirm_kb(req.id),
                )
            except Exception:
                pass

    else:
        await callback.answer(msg.TRANSFER_ACTION_FORBIDDEN, show_alert=True)
        return

    await callback.answer()


@router.callback_query(TransferDecisionCallback.filter(F.action == "reject"))
async def decision_reject(
    callback: CallbackQuery, callback_data: TransferDecisionCallback, session: AsyncSession,
):
    svc = TransferService(session)
    req = await svc.get_request(callback_data.request_id)
    if not req:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    repo = PlayerRepository(session)
    actor = await repo.get_by_telegram_id(callback.from_user.id)
    if not actor:
        await callback.answer()
        return

    player = req.player
    name = f"{player.first_name} {player.last_name}"

    if actor.role == PlayerRole.CAPTAIN:
        if not _captain_can_manage_request(actor, req):
            await callback.answer(msg.TRANSFER_ACTION_FORBIDDEN, show_alert=True)
            return

        req = await svc.captain_reject(callback_data.request_id)
        await callback.message.edit_text(f"❌ Вы отклонили заявку {name}")

        if req.transfer_type.value == "exit":
            try:
                await callback.bot.send_message(
                    chat_id=player.telegram_id,
                    text=msg.TRANSFER_EXIT_CAPTAIN_REJECTED,
                )
            except Exception:
                pass
        elif req.transfer_type.value == "join":
            club_name = req.to_club.name if req.to_club else "—"
            try:
                await callback.bot.send_message(
                    chat_id=player.telegram_id,
                    text=msg.TRANSFER_JOIN_CAPTAIN_REJECTED.format(club=club_name),
                )
            except Exception:
                pass

    elif actor.role == PlayerRole.FREE_AGENT:
        if req.transfer_type.value != "invite" or actor.id != player.id:
            await callback.answer(msg.TRANSFER_ACTION_FORBIDDEN, show_alert=True)
            return

        # FA rejecting invitation
        req = await svc.player_reject_invite(callback_data.request_id)
        await callback.message.edit_text("❌ Вы отклонили приглашение")

        # Notify captain
        captain = await svc.get_captain_of_club(req.to_club_id)
        if captain:
            try:
                await callback.bot.send_message(
                    chat_id=captain.telegram_id,
                    text=msg.TRANSFER_INVITE_PLAYER_REJECTED.format(name=name),
                )
            except Exception:
                pass

    else:
        await callback.answer(msg.TRANSFER_ACTION_FORBIDDEN, show_alert=True)
        return

    await callback.answer()


@router.callback_query(TransferDecisionCallback.filter(F.action == "confirm"))
async def decision_confirm(
    callback: CallbackQuery, callback_data: TransferDecisionCallback,
    session: AsyncSession, admin_ids: list, league_admin_ids: list,
):
    """Player confirms JOIN, or Captain confirms INVITE."""
    svc = TransferService(session)
    req = await svc.get_request(callback_data.request_id)
    if not req:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    repo = PlayerRepository(session)
    actor = await repo.get_by_telegram_id(callback.from_user.id)
    if not actor:
        await callback.answer()
        return

    player = req.player
    name = f"{player.first_name} {player.last_name}"
    club_name = req.to_club.name if req.to_club else "—"

    if req.transfer_type.value == "join" and actor.id == player.id:
        # Player confirming join
        req = await svc.player_confirm_join(callback_data.request_id)
        await callback.message.edit_text(f"✅ Вы подтвердили переход в клуб {club_name}")
        await _notify_admins_transfer(
            callback.bot, admin_ids, league_admin_ids, req, svc, session,
        )

    elif req.transfer_type.value == "invite" and actor.role == PlayerRole.CAPTAIN:
        if not _captain_can_manage_request(actor, req):
            await callback.answer(msg.TRANSFER_ACTION_FORBIDDEN, show_alert=True)
            return

        # Captain final confirm of invite
        req = await svc.captain_confirm_invite(callback_data.request_id)
        await callback.message.edit_text(f"✅ Вы подтвердили вступление {name}")

        # Notify player that captain confirmed, awaiting admin
        try:
            await callback.bot.send_message(
                chat_id=player.telegram_id,
                text=msg.TRANSFER_INVITE_CAPTAIN_CONFIRMED_PLAYER.format(club=club_name),
            )
        except Exception:
            pass

        await _notify_admins_transfer(
            callback.bot, admin_ids, league_admin_ids, req, svc, session,
        )

    else:
        await callback.answer(msg.TRANSFER_ACTION_FORBIDDEN, show_alert=True)
        return

    await callback.answer()


# ========== CAPTAIN: KICK PLAYER (force-remove) ==========

@router.callback_query(TransferActionCallback.filter(F.action == "kick_player"))
async def captain_kick_list(callback: CallbackQuery, session: AsyncSession):
    repo = PlayerRepository(session)
    captain = await repo.get_by_telegram_id(callback.from_user.id)
    if not captain or captain.role != PlayerRole.CAPTAIN or not captain.club_id:
        await callback.answer()
        return

    svc = TransferService(session)
    players = await svc.get_club_players(captain.club_id, exclude_captain_id=captain.id)
    if not players:
        await callback.message.answer(msg.TRANSFER_NO_PLAYERS)
        await callback.answer()
        return

    await callback.message.answer(
        msg.TRANSFER_KICK_LIST_HEADER,
        reply_markup=create_kick_players_kb(players),
    )
    await callback.answer()


@router.callback_query(KickPlayerCallback.filter())
async def captain_kick_player(
    callback: CallbackQuery, callback_data: KickPlayerCallback,
    session: AsyncSession, admin_ids: list, league_admin_ids: list,
):
    repo = PlayerRepository(session)
    captain = await repo.get_by_telegram_id(callback.from_user.id)
    if not captain or captain.role != PlayerRole.CAPTAIN or not captain.club_id:
        await callback.answer()
        return

    target = await repo.get_by_id(callback_data.player_id)
    if not target:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    if target.club_id != captain.club_id or target.role != PlayerRole.PLAYER:
        await callback.answer(msg.TRANSFER_PLAYER_NOT_IN_CLUB, show_alert=True)
        return

    svc = TransferService(session)
    club_repo = ClubRepository(session)
    club = await club_repo.get_by_id(captain.club_id)
    club_name = club.name if club else "—"

    request = await svc.create_kick_request(captain, target.id)
    name = f"{target.first_name} {target.last_name}"
    await callback.message.edit_text(
        msg.TRANSFER_KICK_SENT_ADMIN.format(name=name)
    )

    all_admin_ids = set(admin_ids + league_admin_ids)
    for aid in all_admin_ids:
        try:
            await callback.bot.send_message(
                chat_id=aid,
                text=msg.TRANSFER_KICK_ADMIN_NOTIF.format(name=name, club=club_name),
                reply_markup=create_admin_transfer_kb(request.id),
            )
        except Exception:
            pass

    await callback.answer()


# ========== HELPER: notify admins about pending transfer ==========

async def _notify_admins_transfer(bot, admin_ids, league_admin_ids, req, svc, session):
    player = req.player
    name = f"{player.first_name} {player.last_name}"
    club_repo = ClubRepository(session)

    if req.transfer_type.value == "exit":
        club = await club_repo.get_by_id(req.from_club_id)
        club_name = club.name if club else "—"
        text = msg.TRANSFER_EXIT_ADMIN_NOTIF.format(name=name, club=club_name)
    elif req.transfer_type.value == "join":
        club = await club_repo.get_by_id(req.to_club_id)
        club_name = club.name if club else "—"
        text = msg.TRANSFER_JOIN_PLAYER_CONFIRMED_ADMIN.format(name=name, club=club_name)
    elif req.transfer_type.value == "invite":
        club = await club_repo.get_by_id(req.to_club_id)
        club_name = club.name if club else "—"
        text = msg.TRANSFER_INVITE_CAPTAIN_CONFIRMED_ADMIN.format(name=name, club=club_name)
    else:
        return

    all_admin_ids = set(admin_ids + league_admin_ids)
    for aid in all_admin_ids:
        try:
            await bot.send_message(
                chat_id=aid,
                text=text,
                reply_markup=create_admin_transfer_kb(req.id),
            )
        except Exception:
            pass


def _captain_can_manage_request(actor: Player, req) -> bool:
    if actor.role != PlayerRole.CAPTAIN or not actor.club_id:
        return False

    if req.transfer_type.value == "exit":
        return actor.club_id == req.from_club_id

    if req.transfer_type.value in {"join", "invite"}:
        return actor.club_id == req.to_club_id

    return False


def _render_player_profile(player: Player) -> str:
    rating = player.current_rating
    if rating is None:
        rating = player.prev_season_rating

    return msg.TRANSFER_PLAYER_PROFILE.format(
        name=f"{player.first_name} {player.last_name}",
        position=POSITION_LABELS.get(player.position, "—"),
        rating=rating if rating is not None else "—",
        description=player.description or "—",
    )
