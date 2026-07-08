import csv
import io
from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy import column, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from football_bot.filters.is_admin import IsAnyAdminFilter
from football_bot.keyboards.inline.admin_panel_kb import (
    AdminPanelAction, AdminClubCallback, AdminPlayerCallback,
    create_admin_cancel_kb, create_admin_panel_kb,
    create_admin_clubs_kb, create_admin_players_kb,
)
from football_bot.locales import messages as msg
from football_bot.models import Club
from football_bot.repository import ClubRepository, PlayerRepository, SeasonRatingRepository
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

_computed_ratings_view = table(
    "computed_scraped_player_ratings",
    column("id"),
    column("external_id"),
    column("season_key"),
    column("season_label"),
    column("season_bucket"),
    column("tournament_name"),
    column("division_key"),
    column("first_name"),
    column("last_name"),
    column("position"),
    column("club_id"),
    column("games_played"),
    column("mvp_count"),
    column("goals"),
    column("assists"),
    column("yellow_cards"),
    column("red_cards"),
    column("scraped_rating"),
    column("rating_override"),
    column("rating_override_updated_at"),
    column("wins"),
    column("starts"),
    column("goals_conceded"),
    column("defensive_points"),
    column("computed_rating"),
    column("current_rating"),
    column("division_rank"),
    column("division_total"),
    column("position_rank"),
    column("position_total"),
    column("avg_points_per_game"),
)


def _csv_value(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return value


async def _build_scraped_players_export(session: AsyncSession) -> tuple[str, bytes, int]:
    stmt = (
        select(
            _computed_ratings_view,
            Club.name.label("club_name"),
        )
        .select_from(
            _computed_ratings_view.outerjoin(Club, Club.id == _computed_ratings_view.c.club_id)
        )
        .order_by(
            _computed_ratings_view.c.season_key.desc(),
            _computed_ratings_view.c.season_bucket,
            _computed_ratings_view.c.division_key,
            _computed_ratings_view.c.division_rank,
            _computed_ratings_view.c.external_id,
        )
    )
    result = await session.execute(stmt)
    rating_rows = list(result.mappings().all())

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "id",
        "external_id",
        "season_key",
        "season_label",
        "season_bucket",
        "first_name",
        "last_name",
        "position",
        "club_id",
        "club_name",
        "tournament_name",
        "division_key",
        "games_played",
        "mvp_count",
        "goals",
        "assists",
        "yellow_cards",
        "red_cards",
        "scraped_rating",
        "rating_override",
        "rating_override_updated_at",
        "wins",
        "starts",
        "goals_conceded",
        "defensive_points",
        "computed_rating",
        "current_rating",
        "division_rank",
        "division_total",
        "position_rank",
        "position_total",
        "avg_points_per_game",
    ])
    for row in rating_rows:
        writer.writerow([
            _csv_value(row["id"]),
            _csv_value(row["external_id"]),
            _csv_value(row["season_key"]),
            _csv_value(row["season_label"]),
            _csv_value(row["season_bucket"]),
            _csv_value(row["first_name"]),
            _csv_value(row["last_name"]),
            _csv_value(row["position"]),
            _csv_value(row["club_id"]),
            _csv_value(row["club_name"]),
            _csv_value(row["tournament_name"]),
            _csv_value(row["division_key"]),
            _csv_value(row["games_played"]),
            _csv_value(row["mvp_count"]),
            _csv_value(row["goals"]),
            _csv_value(row["assists"]),
            _csv_value(row["yellow_cards"]),
            _csv_value(row["red_cards"]),
            _csv_value(row["scraped_rating"]),
            _csv_value(row["rating_override"]),
            _csv_value(row["rating_override_updated_at"]),
            _csv_value(row["wins"]),
            _csv_value(row["starts"]),
            _csv_value(row["goals_conceded"]),
            _csv_value(row["defensive_points"]),
            _csv_value(row["computed_rating"]),
            _csv_value(row["current_rating"]),
            _csv_value(row["division_rank"]),
            _csv_value(row["division_total"]),
            _csv_value(row["position_rank"]),
            _csv_value(row["position_total"]),
            _csv_value(row["avg_points_per_game"]),
        ])

    filename = f"computed_player_ratings_{datetime.now(timezone.utc).date().isoformat()}.csv"
    return filename, output.getvalue().encode("utf-8-sig"), len(rating_rows)


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
    rating_repo = SeasonRatingRepository(session)

    if rating_field == "edit_prev_rating":
        updated = await rating_repo.apply_rating_override(
            player,
            season_bucket="previous",
            rating=new_rating,
            updated_at=now,
        )
        if not updated:
            await message.answer(msg.ADMIN_RATING_SEASON_UNAVAILABLE.format(name=name))
            return
        await message.answer(msg.ADMIN_PREV_RATING_UPDATED.format(name=name, rating=new_rating))
        return

    updated = await rating_repo.apply_rating_override(
        player,
        season_bucket="current",
        rating=new_rating,
        updated_at=now,
    )
    if not updated:
        await message.answer(msg.ADMIN_RATING_SEASON_UNAVAILABLE.format(name=name))
        return
    await message.answer(msg.ADMIN_RATING_UPDATED.format(name=name, rating=new_rating))
