from datetime import datetime

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from football_bot.filters.validators import is_valid_name, is_valid_date
from football_bot.keyboards.inline.registration_kb import (
    create_position_kb, create_status_kb, create_tournament_kb,
    create_club_kb, create_role_kb, create_skip_kb,
    PositionCallback, TournamentCallback, ClubCallback,
)
from football_bot.keyboards.inline.admin_kb import create_admin_reg_kb
from football_bot.locales import messages as msg
from football_bot.models import PlayerRole, PlayerPosition
from football_bot.repository import TournamentRepository, ClubRepository
from football_bot.service import RegistrationService
from football_bot.states import FSMRegistration

router = Router()


# --- Entry point: "Регистрация" button ---

@router.callback_query(F.data == "registration")
async def start_registration(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    svc = RegistrationService(session)
    player = await svc.get_player(callback.from_user.id)

    if player and player.registration_status.value == "pending":
        await callback.answer(msg.NOTIF_REG_PENDING_ALERT, show_alert=True)
        return

    if player and player.registration_status.value == "approved":
        await callback.answer(msg.ERR_ALREADY_REGISTERED, show_alert=True)
        return

    # Remove the start keyboard so the "Регистрация" button disappears immediately
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.answer(msg.REG_ENTER_FIRST_NAME)
    await state.set_state(FSMRegistration.enter_first_name)
    await callback.answer()


# --- Step 1: First name ---

@router.message(StateFilter(FSMRegistration.enter_first_name))
async def process_first_name(message: Message, state: FSMContext):
    if not is_valid_name(message.text):
        await message.answer(msg.ERR_INVALID_NAME)
        return
    await state.update_data(first_name=message.text.strip())
    await message.answer(msg.REG_ENTER_LAST_NAME)
    await state.set_state(FSMRegistration.enter_last_name)


# --- Step 2: Last name ---

@router.message(StateFilter(FSMRegistration.enter_last_name))
async def process_last_name(message: Message, state: FSMContext):
    if not is_valid_name(message.text):
        await message.answer(msg.ERR_INVALID_SURNAME)
        return
    await state.update_data(last_name=message.text.strip())
    await message.answer(msg.REG_CHOOSE_POSITION, reply_markup=create_position_kb())
    await state.set_state(FSMRegistration.choose_position)


# --- Step 3: Position ---

@router.callback_query(PositionCallback.filter(), StateFilter(FSMRegistration.choose_position))
async def process_position(callback: CallbackQuery, callback_data: PositionCallback, state: FSMContext):
    await state.update_data(position=callback_data.position)
    await callback.message.answer(msg.REG_ENTER_DESCRIPTION, reply_markup=create_skip_kb())
    await state.set_state(FSMRegistration.enter_description)
    await callback.answer()


# --- Step 4: Description (optional) ---

@router.callback_query(F.data == "skip", StateFilter(FSMRegistration.enter_description))
async def skip_description(callback: CallbackQuery, state: FSMContext):
    await state.update_data(description=None)
    await callback.message.answer(msg.REG_ENTER_BIRTH_DATE)
    await state.set_state(FSMRegistration.enter_birth_date)
    await callback.answer()


@router.message(StateFilter(FSMRegistration.enter_description))
async def process_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await message.answer(msg.REG_ENTER_BIRTH_DATE)
    await state.set_state(FSMRegistration.enter_birth_date)


# --- Step 5: Birth date ---

@router.message(StateFilter(FSMRegistration.enter_birth_date))
async def process_birth_date(message: Message, state: FSMContext):
    if not is_valid_date(message.text):
        await message.answer(msg.ERR_INVALID_DATE)
        return
    date_obj = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    await state.update_data(birth_date=date_obj.isoformat())
    await message.answer(msg.REG_UPLOAD_PHOTO)
    await state.set_state(FSMRegistration.upload_photo)


# --- Step 6: Photo ---

@router.message(StateFilter(FSMRegistration.upload_photo), F.photo)
async def process_photo(message: Message, state: FSMContext):
    photo = message.photo[-1]  # largest resolution
    await state.update_data(photo_file_id=photo.file_id)
    await message.answer(msg.REG_CHOOSE_STATUS, reply_markup=create_status_kb())
    await state.set_state(FSMRegistration.choose_status)


@router.message(StateFilter(FSMRegistration.upload_photo))
async def process_photo_invalid(message: Message):
    await message.answer(msg.ERR_INVALID_PHOTO)


# --- Step 7a: Free agent path ---

@router.callback_query(F.data == "status_free_agent", StateFilter(FSMRegistration.choose_status))
async def status_free_agent(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession,
    admin_ids: list, league_admin_ids: list,
):
    data = await state.get_data()
    svc = RegistrationService(session)
    player = await svc.create_registration(
        telegram_id=callback.from_user.id,
        telegram_username=callback.from_user.username,
        first_name=data["first_name"],
        last_name=data["last_name"],
        position=PlayerPosition(data["position"]),
        description=data.get("description"),
        birth_date=datetime.fromisoformat(data["birth_date"]).date(),
        photo_file_id=data["photo_file_id"],
        role=PlayerRole.FREE_AGENT,
        club_id=None,
    )
    await callback.message.answer(msg.NOTIF_REG_SENT)

    # Notify admins
    all_admin_ids = set(admin_ids + league_admin_ids)
    admin_text = msg.ADMIN_NEW_REG.format(
        name=f"{player.first_name} {player.last_name}",
        status="Свободный агент",
    )
    for aid in all_admin_ids:
        try:
            await callback.bot.send_photo(
                chat_id=aid,
                photo=player.photo_file_id,
                caption=admin_text,
                reply_markup=create_admin_reg_kb(player.id),
            )
        except Exception:
            pass

    await state.clear()
    await callback.answer()


# --- Step 7b: Choose club path ---

@router.callback_query(F.data == "status_choose_club", StateFilter(FSMRegistration.choose_status))
async def status_choose_club(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    repo = TournamentRepository(session)
    tournaments = await repo.get_all()
    if not tournaments:
        await callback.message.answer(
            "Турниры ещё не загружены. Попробуйте позже или выберите «Свободный агент»."
        )
        await callback.answer()
        return
    await callback.message.answer(msg.REG_CHOOSE_TOURNAMENT, reply_markup=create_tournament_kb(tournaments))
    await state.set_state(FSMRegistration.choose_tournament)
    await callback.answer()


# --- Step 8: Choose tournament ---

@router.callback_query(TournamentCallback.filter(), StateFilter(FSMRegistration.choose_tournament))
async def process_tournament(
    callback: CallbackQuery, callback_data: TournamentCallback,
    state: FSMContext, session: AsyncSession,
):
    await state.update_data(tournament_id=callback_data.tournament_id)
    repo = ClubRepository(session)
    clubs = await repo.get_by_tournament_id(callback_data.tournament_id)
    if not clubs:
        await callback.message.answer("В этом турнире пока нет клубов.")
        await callback.answer()
        return
    await callback.message.answer(msg.REG_CHOOSE_CLUB, reply_markup=create_club_kb(clubs))
    await state.set_state(FSMRegistration.choose_club)
    await callback.answer()


# --- Step 9: Choose club ---

@router.callback_query(ClubCallback.filter(), StateFilter(FSMRegistration.choose_club))
async def process_club(callback: CallbackQuery, callback_data: ClubCallback, state: FSMContext):
    await state.update_data(club_id=callback_data.club_id)
    await callback.message.answer(msg.REG_CHOOSE_ROLE, reply_markup=create_role_kb())
    await state.set_state(FSMRegistration.choose_role)
    await callback.answer()


# --- Step 10: Choose role -> submit ---

@router.callback_query(
    F.data.in_({"role_captain", "role_player"}),
    StateFilter(FSMRegistration.choose_role),
)
async def process_role(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession,
    admin_ids: list, league_admin_ids: list,
):
    role = PlayerRole.CAPTAIN if callback.data == "role_captain" else PlayerRole.PLAYER
    data = await state.get_data()
    svc = RegistrationService(session)
    club_repo = ClubRepository(session)
    club = await club_repo.get_by_id(data["club_id"])

    player = await svc.create_registration(
        telegram_id=callback.from_user.id,
        telegram_username=callback.from_user.username,
        first_name=data["first_name"],
        last_name=data["last_name"],
        position=PlayerPosition(data["position"]),
        description=data.get("description"),
        birth_date=datetime.fromisoformat(data["birth_date"]).date(),
        photo_file_id=data["photo_file_id"],
        role=role,
        club_id=data["club_id"],
    )
    await callback.message.answer(msg.NOTIF_REG_SENT)

    role_label = "Капитан" if role == PlayerRole.CAPTAIN else "Игрок"
    club_name = club.name if club else "—"
    status_str = f"Клуб: {club_name}, Роль: {role_label}"
    admin_text = msg.ADMIN_NEW_REG.format(
        name=f"{player.first_name} {player.last_name}",
        status=status_str,
    )
    all_admin_ids = set(admin_ids + league_admin_ids)
    for aid in all_admin_ids:
        try:
            await callback.bot.send_photo(
                chat_id=aid,
                photo=player.photo_file_id,
                caption=admin_text,
                reply_markup=create_admin_reg_kb(player.id),
            )
        except Exception:
            pass

    await state.clear()
    await callback.answer()
