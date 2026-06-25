from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData


class TournamentCallback(CallbackData, prefix="tourn"):
    tournament_id: int


class ClubCallback(CallbackData, prefix="club"):
    club_id: int


class PositionCallback(CallbackData, prefix="pos"):
    position: str


def create_position_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    positions = [
        ("Вратарь", "goalkeeper"),
        ("Защитник", "defender"),
        ("Оборонительный полузащитник", "defensive_midfielder"),
        ("Атакующий полузащитник", "attacking_midfielder"),
        ("Нападающий", "forward"),
    ]
    for label, value in positions:
        builder.row(InlineKeyboardButton(
            text=label,
            callback_data=PositionCallback(position=value).pack(),
        ))
    return builder.as_markup()


def create_status_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Свободный агент", callback_data="status_free_agent"),
    )
    builder.row(
        InlineKeyboardButton(text="Выбор клуба", callback_data="status_choose_club"),
    )
    return builder.as_markup()


def create_tournament_kb(tournaments: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for t in tournaments:
        builder.row(InlineKeyboardButton(
            text=t.name,
            callback_data=TournamentCallback(tournament_id=t.id).pack(),
        ))
    return builder.as_markup()


def create_club_kb(clubs: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for club in clubs:
        builder.row(InlineKeyboardButton(
            text=club.name,
            callback_data=ClubCallback(club_id=club.id).pack(),
        ))
    return builder.as_markup()


def create_role_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Капитан", callback_data="role_captain"),
        InlineKeyboardButton(text="Игрок", callback_data="role_player"),
    )
    return builder.as_markup()


def create_skip_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Пропустить", callback_data="skip"))
    return builder.as_markup()
