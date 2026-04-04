from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from football_bot.filters.is_admin import IsAnyAdminFilter
from football_bot.keyboards.inline.transfer_kb import AdminTransferAction
from football_bot.keyboards.reply.main_menu import (
    create_player_menu, create_free_agent_menu,
)
from football_bot.locales import messages as msg
from football_bot.models import TransferType
from football_bot.service import TransferService

router = Router()
router.callback_query.filter(IsAnyAdminFilter())


@router.callback_query(AdminTransferAction.filter(F.action == "approve"))
async def admin_approve_transfer(
    callback: CallbackQuery, callback_data: AdminTransferAction, session: AsyncSession,
):
    svc = TransferService(session)
    req = await svc.get_request(callback_data.request_id)
    if not req:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    req = await svc.admin_approve(callback_data.request_id)
    player = req.player
    name = f"{player.first_name} {player.last_name}"
    captain = await _resolve_captain_for_request(svc, req)

    await callback.message.edit_text(f"✅ Трансфер одобрен: {name}")

    # Notify player
    if req.transfer_type.value in ("exit", "kick"):
        club_name = req.from_club.name if req.from_club else "—"
        notify_text = (
            msg.TRANSFER_EXIT_ADMIN_APPROVED
            if req.transfer_type.value == "exit"
            else msg.TRANSFER_KICK_ADMIN_APPROVED.format(club=club_name)
        )
        try:
            await callback.bot.send_message(
                chat_id=player.telegram_id,
                text=notify_text,
                reply_markup=create_free_agent_menu(),
            )
        except Exception:
            pass

    elif req.transfer_type.value in ("join", "invite"):
        club_name = req.to_club.name if req.to_club else "—"
        notify_msg = (
            msg.TRANSFER_JOIN_ADMIN_APPROVED
            if req.transfer_type.value == "join"
            else msg.TRANSFER_INVITE_ADMIN_APPROVED
        )
        try:
            await callback.bot.send_message(
                chat_id=player.telegram_id,
                text=notify_msg.format(club=club_name),
                reply_markup=create_player_menu(),
            )
        except Exception:
            pass

    await _notify_captain_decision(
        callback, captain, req.transfer_type, approved=True, name=name,
    )
    await callback.answer(msg.ADMIN_TRANSFER_APPROVED)


@router.callback_query(AdminTransferAction.filter(F.action == "reject"))
async def admin_reject_transfer(
    callback: CallbackQuery, callback_data: AdminTransferAction, session: AsyncSession,
):
    svc = TransferService(session)
    req = await svc.get_request(callback_data.request_id)
    if not req:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    req = await svc.admin_reject(callback_data.request_id)
    player = req.player
    name = f"{player.first_name} {player.last_name}"
    captain = await _resolve_captain_for_request(svc, req)

    await callback.message.edit_text(f"❌ Трансфер отклонён: {name}")

    # Notify player
    if req.transfer_type.value in ("exit", "kick"):
        notify_text = (
            msg.TRANSFER_EXIT_ADMIN_REJECTED
            if req.transfer_type.value == "exit"
            else msg.TRANSFER_KICK_ADMIN_REJECTED
        )
        try:
            await callback.bot.send_message(
                chat_id=player.telegram_id,
                text=notify_text,
            )
        except Exception:
            pass

    elif req.transfer_type.value in ("join", "invite"):
        club_name = req.to_club.name if req.to_club else "—"
        notify_msg = (
            msg.TRANSFER_JOIN_ADMIN_REJECTED
            if req.transfer_type.value == "join"
            else msg.TRANSFER_INVITE_ADMIN_REJECTED
        )
        try:
            await callback.bot.send_message(
                chat_id=player.telegram_id,
                text=notify_msg.format(club=club_name),
            )
        except Exception:
            pass

    await _notify_captain_decision(
        callback, captain, req.transfer_type, approved=False, name=name,
    )
    await callback.answer(msg.ADMIN_TRANSFER_REJECTED)


async def _resolve_captain_for_request(svc: TransferService, req):
    if req.transfer_type in (TransferType.JOIN, TransferType.INVITE):
        if req.to_club_id:
            return await svc.get_captain_of_club(req.to_club_id)
        return None

    if req.transfer_type == TransferType.KICK:
        return await svc.get_player_by_telegram_id(req.initiated_by)

    if req.from_club_id:
        return await svc.get_captain_of_club(req.from_club_id)
    return None


async def _notify_captain_decision(callback, captain, transfer_type, approved: bool, name: str) -> None:
    if not captain:
        return

    if transfer_type == TransferType.EXIT:
        text = (
            msg.TRANSFER_EXIT_ADMIN_APPROVED_CAPTAIN
            if approved else msg.TRANSFER_EXIT_ADMIN_REJECTED_CAPTAIN
        ).format(name=name)
    elif transfer_type == TransferType.JOIN:
        text = (
            msg.TRANSFER_JOIN_ADMIN_APPROVED_CAPTAIN
            if approved else msg.TRANSFER_JOIN_ADMIN_REJECTED_CAPTAIN
        ).format(name=name)
    elif transfer_type == TransferType.INVITE:
        text = (
            msg.TRANSFER_INVITE_ADMIN_APPROVED_CAPTAIN
            if approved else msg.TRANSFER_INVITE_ADMIN_REJECTED_CAPTAIN
        ).format(name=name)
    elif transfer_type == TransferType.KICK:
        text = (
            msg.TRANSFER_KICK_ADMIN_APPROVED_CAPTAIN
            if approved else msg.TRANSFER_KICK_ADMIN_REJECTED_CAPTAIN
        ).format(name=name)
    else:
        return

    try:
        await callback.bot.send_message(chat_id=captain.telegram_id, text=text)
    except Exception:
        pass
