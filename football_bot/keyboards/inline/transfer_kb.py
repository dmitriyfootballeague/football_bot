from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData


class TransferActionCallback(CallbackData, prefix="tr_act"):
    action: str


class TransferDecisionCallback(CallbackData, prefix="tr_dec"):
    request_id: int
    action: str  # approve / reject / confirm


class TransferPlayerCallback(CallbackData, prefix="tr_player"):
    player_id: int


# --- Role-specific transfer menus ---

def create_player_transfer_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="Стать свободным агентом",
        callback_data=TransferActionCallback(action="exit").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text="Выбор дивизиона и клуба",
        callback_data=TransferActionCallback(action="join").pack(),
    ))
    return builder.as_markup()


def create_free_agent_transfer_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="Приглашения от клубов",
        callback_data=TransferActionCallback(action="invitations").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text="Самостоятельный выбор клуба",
        callback_data=TransferActionCallback(action="join").pack(),
    ))
    return builder.as_markup()


def create_captain_transfer_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="Свободные агенты",
        callback_data=TransferActionCallback(action="free_agents").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text="Запросы на трансфер",
        callback_data=TransferActionCallback(action="join_requests").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text="Запросы на выход из клуба",
        callback_data=TransferActionCallback(action="exit_requests").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text="Удалить игрока из команды",
        callback_data=TransferActionCallback(action="kick_player").pack(),
    ))
    return builder.as_markup()


# --- Decision keyboards ---

def create_transfer_decision_kb(request_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Принять",
            callback_data=TransferDecisionCallback(request_id=request_id, action="approve").pack(),
        ),
        InlineKeyboardButton(
            text="❌ Отклонить",
            callback_data=TransferDecisionCallback(request_id=request_id, action="reject").pack(),
        ),
    )
    return builder.as_markup()


def create_transfer_confirm_kb(request_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="✅ Подтвердить переход",
        callback_data=TransferDecisionCallback(request_id=request_id, action="confirm").pack(),
    ))
    return builder.as_markup()


def create_invite_kb(player_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="Пригласить в команду",
        callback_data=TransferPlayerCallback(player_id=player_id).pack(),
    ))
    return builder.as_markup()


def create_free_agents_list_kb(players: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in players:
        builder.row(InlineKeyboardButton(
            text=f"{p.first_name} {p.last_name}",
            callback_data=TransferPlayerCallback(player_id=p.id).pack(),
        ))
    return builder.as_markup()


# --- Captain kick (force-remove) ---

class KickPlayerCallback(CallbackData, prefix="tr_kick"):
    player_id: int


def create_kick_players_kb(players: list) -> InlineKeyboardMarkup:
    """List of club players the captain can force-remove."""
    builder = InlineKeyboardBuilder()
    for p in players:
        builder.row(InlineKeyboardButton(
            text=f"❌ {p.first_name} {p.last_name}",
            callback_data=KickPlayerCallback(player_id=p.id).pack(),
        ))
    return builder.as_markup()


# --- Admin transfer decision ---

class AdminTransferAction(CallbackData, prefix="admin_tr"):
    action: str  # approve / reject
    request_id: int


def create_admin_transfer_kb(request_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Одобрить",
            callback_data=AdminTransferAction(action="approve", request_id=request_id).pack(),
        ),
        InlineKeyboardButton(
            text="❌ Отклонить",
            callback_data=AdminTransferAction(action="reject", request_id=request_id).pack(),
        ),
    )
    return builder.as_markup()
