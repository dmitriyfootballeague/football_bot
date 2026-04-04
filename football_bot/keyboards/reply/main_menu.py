from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def create_player_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Рейтинг"), KeyboardButton(text="Трансфер")],
        ],
        resize_keyboard=True,
    )


def create_free_agent_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Рейтинг за прошлый сезон"), KeyboardButton(text="Трансфер")],
        ],
        resize_keyboard=True,
    )


def create_captain_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Рейтинг"), KeyboardButton(text="Трансфер")],
        ],
        resize_keyboard=True,
    )
