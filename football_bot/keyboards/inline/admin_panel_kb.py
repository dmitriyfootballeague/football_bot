from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


class AdminPanelAction(CallbackData, prefix="adm_panel"):
    action: str  # edit_club / edit_rating / edit_prev_rating


class AdminClubCallback(CallbackData, prefix="adm_club"):
    club_id: int


class AdminPlayerCallback(CallbackData, prefix="adm_plr"):
    player_id: int


def create_admin_panel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="✏️ Редактировать клуб",
        callback_data=AdminPanelAction(action="edit_club").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text="⭐ Изменить рейтинг игрока",
        callback_data=AdminPanelAction(action="edit_rating").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text="📅 Изменить рейтинг за прошлый сезон",
        callback_data=AdminPanelAction(action="edit_prev_rating").pack(),
    ))
    return builder.as_markup()


def create_admin_clubs_kb(clubs: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for club in clubs:
        builder.row(InlineKeyboardButton(
            text=club.name,
            callback_data=AdminClubCallback(club_id=club.id).pack(),
        ))
    return builder.as_markup()


def create_admin_players_kb(players: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in players:
        builder.row(InlineKeyboardButton(
            text=f"{p.first_name} {p.last_name}",
            callback_data=AdminPlayerCallback(player_id=p.id).pack(),
        ))
    return builder.as_markup()
