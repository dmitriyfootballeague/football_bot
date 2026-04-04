from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from football_bot.filters.is_admin import IsAnyAdminFilter
from football_bot.keyboards.inline.admin_kb import AdminRegAction
from football_bot.keyboards.reply.main_menu import (
    create_player_menu, create_free_agent_menu, create_captain_menu,
)
from football_bot.locales import messages as msg
from football_bot.models import PlayerRole
from football_bot.repository import PlayerRepository, ClubRepository

router = Router()
router.callback_query.filter(IsAnyAdminFilter())


@router.callback_query(AdminRegAction.filter(F.action == "approve"))
async def approve_registration(
    callback: CallbackQuery, callback_data: AdminRegAction, session: AsyncSession,
):
    repo = PlayerRepository(session)
    player = await repo.get_by_id(callback_data.player_id)
    if not player:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    from football_bot.models import RegistrationStatus
    await repo.update_registration_status(player.id, RegistrationStatus.APPROVED)

    # Build status string for user notification
    if player.role == PlayerRole.FREE_AGENT:
        status_str = "Свободный агент"
    else:
        club_repo = ClubRepository(session)
        club = await club_repo.get_by_id(player.club_id)
        club_name = club.name if club else "—"
        status_str = f"Игрок клуба: {club_name}"

    # Send role-based menu to user
    menu_map = {
        PlayerRole.CAPTAIN: create_captain_menu,
        PlayerRole.PLAYER: create_player_menu,
        PlayerRole.FREE_AGENT: create_free_agent_menu,
    }
    menu_fn = menu_map.get(player.role, create_player_menu)

    try:
        await callback.bot.send_message(
            chat_id=player.telegram_id,
            text=msg.NOTIF_REG_APPROVED.format(status=status_str),
            reply_markup=menu_fn(),
        )
    except Exception:
        pass

    await callback.message.edit_caption(
        caption=f"✅ ОДОБРЕНО: {player.first_name} {player.last_name}"
    )
    await callback.answer("Регистрация подтверждена")


@router.callback_query(AdminRegAction.filter(F.action == "reject"))
async def reject_registration(
    callback: CallbackQuery, callback_data: AdminRegAction, session: AsyncSession,
):
    repo = PlayerRepository(session)
    player = await repo.get_by_id(callback_data.player_id)

    from football_bot.models import RegistrationStatus
    await repo.update_registration_status(callback_data.player_id, RegistrationStatus.REJECTED)

    if player:
        try:
            await callback.bot.send_message(
                chat_id=player.telegram_id,
                text=msg.NOTIF_REG_REJECTED,
            )
        except Exception:
            pass

    name = f"{player.first_name} {player.last_name}" if player else "—"
    await callback.message.edit_caption(caption=f"❌ ОТКЛОНЕНО: {name}")
    await callback.answer("Регистрация отклонена")
