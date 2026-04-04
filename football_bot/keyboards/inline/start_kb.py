from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def create_start_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Регистрация", callback_data="registration"),
        InlineKeyboardButton(text="Инструкция", callback_data="instruction"),
    )
    return builder.as_markup()


def create_reapply_kb() -> InlineKeyboardMarkup:
    """Shown to players whose registration was rejected — lets them re-apply."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Подать заявку", callback_data="registration"),
        InlineKeyboardButton(text="Инструкция", callback_data="instruction"),
    )
    return builder.as_markup()
