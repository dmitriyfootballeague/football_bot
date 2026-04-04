from datetime import date

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from football_bot.locales import messages as msg
from football_bot.models import PlayerPosition, PlayerRole, RegistrationStatus
from football_bot.repository import ClubRepository
from football_bot.service import RatingService

router = Router()

POSITION_LABELS = {
    PlayerPosition.GOALKEEPER: "Вратарь",
    PlayerPosition.DEFENDER: "Защитник",
    PlayerPosition.MIDFIELDER: "Полузащитник",
    PlayerPosition.FORWARD: "Нападающий",
}


@router.message(F.text == "Рейтинг")
async def show_rating(message: Message, session: AsyncSession):
    svc = RatingService(session)
    player = await svc.get_player_rating(message.from_user.id)
    if not player or player.registration_status != RegistrationStatus.APPROVED:
        await message.answer(msg.RATING_UNAVAILABLE)
        return

    club_name = "—"
    tournament_name = "—"
    if player.club_id:
        club_repo = ClubRepository(session)
        club = await club_repo.get_by_id(player.club_id)
        if club:
            club_name = club.name
            tournament_name = club.tournament.name if club.tournament else "—"

    age = (date.today() - player.birth_date).days // 365

    text = msg.RATING_TEMPLATE.format(
        full_name=f"{player.first_name} {player.last_name}",
        position=POSITION_LABELS.get(player.position, "—"),
        age=age,
        club=club_name,
        tournament=tournament_name,
        description=player.description or "—",
        rating=player.current_rating or "—",
        div_rank=player.division_rank or "—",
        div_total=player.division_total or "—",
        pos_rank=player.position_rank or "—",
        pos_total=player.position_total or "—",
        avg_points=player.avg_points_per_game or "—",
        updated_at=(
            player.rating_updated_at.strftime("%d.%m.%Y")
            if player.rating_updated_at else "—"
        ),
    )
    await message.answer(text)


@router.message(F.text == "Рейтинг за прошлый сезон")
async def show_prev_rating(message: Message, session: AsyncSession):
    svc = RatingService(session)
    player = await svc.get_player_rating(message.from_user.id)
    if not player or player.registration_status != RegistrationStatus.APPROVED:
        await message.answer(msg.RATING_UNAVAILABLE)
        return

    age = (date.today() - player.birth_date).days // 365

    text = msg.RATING_PREV_TEMPLATE.format(
        full_name=f"{player.first_name} {player.last_name}",
        position=POSITION_LABELS.get(player.position, "—"),
        age=age,
        description=player.description or "—",
        rating=player.prev_season_rating or "—",
        div_rank=player.prev_division_rank or "—",
        div_total=player.prev_division_total or "—",
        pos_rank=player.prev_position_rank or "—",
        pos_total=player.prev_position_total or "—",
        avg_points=player.prev_avg_points or "—",
        updated_at=(
            player.prev_rating_updated_at.strftime("%d.%m.%Y")
            if player.prev_rating_updated_at else "—"
        ),
    )
    await message.answer(text)
