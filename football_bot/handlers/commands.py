from aiogram import Router, types
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import any_state
from sqlalchemy.ext.asyncio import AsyncSession

from football_bot.keyboards.inline.start_kb import create_start_kb, create_reapply_kb
from football_bot.keyboards.reply.main_menu import (
    create_player_menu, create_free_agent_menu, create_captain_menu,
)
from football_bot.locales import messages as msg
from football_bot.models import RegistrationStatus, PlayerRole
from football_bot.service import RegistrationService

router = Router()


@router.message(CommandStart(), StateFilter(any_state))
async def cmd_start(message: types.Message, state: FSMContext, session: AsyncSession):
    await state.clear()
    if message.from_user is None:
        return

    svc = RegistrationService(session)
    player = await svc.get_player(message.from_user.id)

    if player and player.registration_status == RegistrationStatus.APPROVED:
        menu_map = {
            PlayerRole.CAPTAIN: create_captain_menu,
            PlayerRole.PLAYER: create_player_menu,
            PlayerRole.FREE_AGENT: create_free_agent_menu,
        }
        menu_fn = menu_map.get(player.role, create_player_menu)
        await message.answer(
            f"С возвращением, {player.first_name}!",
            reply_markup=menu_fn(),
        )
        return

    if player and player.registration_status == RegistrationStatus.PENDING:
        await message.answer(msg.NOTIF_REG_PENDING)
        return

    if player and player.registration_status == RegistrationStatus.REJECTED:
        await message.answer(msg.NOTIF_REG_REJECTED_REAPPLY, reply_markup=create_reapply_kb())
        return

    # Truly new user
    await message.answer(msg.WELCOME_MESSAGE, reply_markup=create_start_kb())


@router.message(Command("cancel"), StateFilter(any_state))
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы сбросили все действия и состояния.")


@router.message(Command("help"), StateFilter(any_state))
async def cmd_help(message: types.Message):
    await message.answer(
        "Доступные команды:\n/start - начать\n/cancel - отменить текущее действие"
    )
