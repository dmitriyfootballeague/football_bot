import csv
import io
from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from football_bot.filters.is_admin import IsAnyAdminFilter
from football_bot.keyboards.inline.admin_panel_kb import (
    AdminPanelAction, AdminClubCallback, AdminPlayerCallback,
    create_admin_cancel_kb, create_admin_panel_kb,
    create_admin_clubs_kb, create_admin_players_kb,
)
from football_bot.locales import messages as msg
from football_bot.models import Club, ScrapedPlayerStats
from football_bot.repository import ClubRepository, PlayerRepository
from football_bot.states import FSMAdminEditClub, FSMAdminEditRating


router = Router()
router.message.filter(IsAnyAdminFilter())
router.callback_query.filter(IsAnyAdminFilter())

ADMIN_EDIT_STATES = (
    FSMAdminEditClub.choose_club,
    FSMAdminEditClub.enter_new_name,
    FSMAdminEditRating.choose_player,
    FSMAdminEditRating.enter_rating,
)


async def _build_scraped_players_export(session: AsyncSession) -> tuple[str, bytes, int]:
    stmt = (
        select(ScrapedPlayerStats)
        .options(
            selectinload(ScrapedPlayerStats.club).selectinload(Club.tournament)
        )
        .order_by(ScrapedPlayerStats.id)
    )
    result = await session.execute(stmt)
    scraped_players = list(result.scalars().all())

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "id",
        "external_id",
        "first_name",
        "last_name",
        "position",
        "club_id",
        "club_name",
        "tournament_name",
        "games_played",
        "mvp_count",
        "goals",
        "assists",
        "yellow_cards",
        "red_cards",
        "current_rating",
        "division_rank",
        "division_total",
        "avg_points_per_game",
        "created_at",
        "updated_at",
    ])
    for player in scraped_players:
        club = player.club
        tournament = club.tournament if club else None
        writer.writerow([
            player.id,
            player.external_id,
            player.first_name,
            player.last_name,
            player.position.value if player.position else "",
            player.club_id or "",
            club.name if club else "",
            tournament.name if tournament else "",
            player.games_played,
            player.mvp_count,
            player.goals,
            player.assists,
            player.yellow_cards,
            player.red_cards,
            player.current_rating if player.current_rating is not None else "",
            player.division_rank if player.division_rank is not None else "",
            player.division_total if player.division_total is not None else "",
            player.avg_points_per_game if player.avg_points_per_game is not None else "",
            player.created_at.isoformat() if player.created_at else "",
            player.updated_at.isoformat() if player.updated_at else "",
        ])

    filename = f"scraped_players_stats_{datetime.now(timezone.utc).date().isoformat()}.csv"
    return filename, output.getvalue().encode("utf-8-sig"), len(scraped_players)


@router.message(Command("admin"))
async def admin_panel(message: Message):
    await message.answer(msg.ADMIN_PANEL_HEADER, reply_markup=create_admin_panel_kb())


@router.callback_query(
    AdminPanelAction.filter(F.action == "cancel"),
    StateFilter(*ADMIN_EDIT_STATES),
)
async def admin_cancel_action(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(
        msg.ADMIN_ACTION_CANCELLED,
        reply_markup=create_admin_panel_kb(),
    )
    await callback.answer()


@router.callback_query(AdminPanelAction.filter(F.action == "export_all_players"))
async def admin_export_all_players(callback: CallbackQuery, session: AsyncSession):
    filename, payload, row_count = await _build_scraped_players_export(session)
    await callback.message.answer_document(
        BufferedInputFile(payload, filename=filename),
        caption=msg.ADMIN_ALL_PLAYERS_EXPORTED.format(count=row_count),
    )
    await callback.answer()


# ========== EDIT CLUB NAME ==========

@router.callback_query(AdminPanelAction.filter(F.action == "edit_club"))
async def admin_edit_club_start(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    repo = ClubRepository(session)
    clubs = await repo.get_all()
    if not clubs:
        await callback.message.answer(msg.ADMIN_NO_CLUBS)
        await callback.answer()
        return

    await callback.message.answer(msg.ADMIN_CHOOSE_CLUB, reply_markup=create_admin_clubs_kb(clubs))
    await state.set_state(FSMAdminEditClub.choose_club)
    await callback.answer()


@router.callback_query(AdminClubCallback.filter(), StateFilter(FSMAdminEditClub.choose_club))
async def admin_edit_club_chosen(
    callback: CallbackQuery, callback_data: AdminClubCallback,
    state: FSMContext, session: AsyncSession,
):
    repo = ClubRepository(session)
    club = await repo.get_by_id(callback_data.club_id)
    if not club:
        await callback.answer("Клуб не найден", show_alert=True)
        return

    await state.update_data(club_id=callback_data.club_id)
    await callback.message.answer(
        msg.ADMIN_ENTER_CLUB_NAME,
        reply_markup=create_admin_cancel_kb(),
    )
    await state.set_state(FSMAdminEditClub.enter_new_name)
    await callback.answer()


@router.message(StateFilter(FSMAdminEditClub.enter_new_name))
async def admin_edit_club_name(message: Message, state: FSMContext, session: AsyncSession):
    new_name = message.text.strip() if message.text else ""
    if not new_name:
        await message.answer(
            msg.ADMIN_ENTER_CLUB_NAME,
            reply_markup=create_admin_cancel_kb(),
        )
        return

    data = await state.get_data()
    club_id = data.get("club_id")
    await state.clear()

    repo = ClubRepository(session)
    await repo.update_name(club_id, new_name)
    await message.answer(msg.ADMIN_CLUB_UPDATED.format(name=new_name))


# ========== EDIT PLAYER RATING ==========

@router.callback_query(AdminPanelAction.filter(F.action.in_({"edit_rating", "edit_prev_rating"})))
async def admin_edit_rating_start(
    callback: CallbackQuery,
    callback_data: AdminPanelAction,
    session: AsyncSession,
    state: FSMContext,
):
    repo = PlayerRepository(session)
    players = await repo.get_all_approved()
    if not players:
        await callback.message.answer(msg.ADMIN_NO_PLAYERS)
        await callback.answer()
        return

    await callback.message.answer(
        msg.ADMIN_CHOOSE_PLAYER,
        reply_markup=create_admin_players_kb(players),
    )
    await state.update_data(rating_field=callback_data.action)
    await state.set_state(FSMAdminEditRating.choose_player)
    await callback.answer()


@router.callback_query(AdminPlayerCallback.filter(), StateFilter(FSMAdminEditRating.choose_player))
async def admin_edit_rating_chosen(
    callback: CallbackQuery, callback_data: AdminPlayerCallback,
    state: FSMContext, session: AsyncSession,
):
    repo = PlayerRepository(session)
    player = await repo.get_by_id(callback_data.player_id)
    if not player:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    data = await state.get_data()
    rating_field = data.get("rating_field", "edit_rating")
    await state.update_data(player_id=callback_data.player_id)
    name = f"{player.first_name} {player.last_name}"
    prompt = (
        msg.ADMIN_ENTER_PREV_RATING
        if rating_field == "edit_prev_rating"
        else msg.ADMIN_ENTER_RATING
    )
    await callback.message.answer(
        prompt.format(name=name),
        reply_markup=create_admin_cancel_kb(),
    )
    await state.set_state(FSMAdminEditRating.enter_rating)
    await callback.answer()


@router.message(StateFilter(FSMAdminEditRating.enter_rating))
async def admin_edit_rating_value(message: Message, state: FSMContext, session: AsyncSession):
    try:
        new_rating = float(message.text.strip().replace(",", "."))
    except (ValueError, AttributeError):
        await message.answer(
            msg.ADMIN_INVALID_RATING,
            reply_markup=create_admin_cancel_kb(),
        )
        return

    data = await state.get_data()
    player_id = data.get("player_id")
    rating_field = data.get("rating_field", "edit_rating")
    await state.clear()

    repo = PlayerRepository(session)
    player = await repo.get_by_id(player_id)
    if not player:
        await message.answer("Игрок не найден.")
        return

    name = f"{player.first_name} {player.last_name}"
    now = datetime.now(timezone.utc)

    if rating_field == "edit_prev_rating":
        await repo.update_rating_data(
            player_id,
            prev_season_rating=new_rating,
            prev_rating_updated_at=now,
        )
        await message.answer(msg.ADMIN_PREV_RATING_UPDATED.format(name=name, rating=new_rating))
        return

    await repo.update_rating_data(
        player_id,
        current_rating=new_rating,
        rating_updated_at=now,
    )
    await message.answer(msg.ADMIN_RATING_UPDATED.format(name=name, rating=new_rating))
