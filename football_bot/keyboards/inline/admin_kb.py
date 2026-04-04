from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData


class AdminRegAction(CallbackData, prefix="admin_reg"):
    action: str  # approve / reject
    player_id: int


def create_admin_reg_kb(player_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Подтвердить",
            callback_data=AdminRegAction(action="approve", player_id=player_id).pack(),
        ),
        InlineKeyboardButton(
            text="❌ Отклонить",
            callback_data=AdminRegAction(action="reject", player_id=player_id).pack(),
        ),
    )
    return builder.as_markup()
