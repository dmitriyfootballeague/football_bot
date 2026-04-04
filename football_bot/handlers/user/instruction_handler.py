from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from football_bot.locales import messages as msg
from football_bot.models import PlayerRole, RegistrationStatus
from football_bot.repository import PlayerRepository

router = Router()

_ROLE_INSTRUCTION = {
    PlayerRole.CAPTAIN: msg.INSTRUCTION_CAPTAIN,
    PlayerRole.PLAYER: msg.INSTRUCTION_PLAYER,
    PlayerRole.FREE_AGENT: msg.INSTRUCTION_FREE_AGENT,
}


@router.callback_query(F.data == "instruction")
async def show_instruction(callback: CallbackQuery, session: AsyncSession):
    repo = PlayerRepository(session)
    player = await repo.get_by_telegram_id(callback.from_user.id)

    if player and player.registration_status == RegistrationStatus.APPROVED:
        # Show only the instruction relevant to the player's role
        text = _ROLE_INSTRUCTION.get(player.role)
        if text:
            await callback.message.answer(text)
            await callback.answer()
            return

    # Not registered or pending — show all three instructions
    await callback.message.answer(msg.INSTRUCTION_CAPTAIN)
    await callback.message.answer(msg.INSTRUCTION_PLAYER)
    await callback.message.answer(msg.INSTRUCTION_FREE_AGENT)
    await callback.answer()
