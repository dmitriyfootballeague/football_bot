from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    BigInteger, Integer, String, Text, Date, DateTime,
    ForeignKey, Enum, Float, Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class PlayerRole(str, enum.Enum):
    PLAYER = "player"
    CAPTAIN = "captain"
    FREE_AGENT = "free_agent"


class PlayerPosition(str, enum.Enum):
    GOALKEEPER = "goalkeeper"
    DEFENDER = "defender"
    DEFENSIVE_MIDFIELDER = "defensive_midfielder"
    ATTACKING_MIDFIELDER = "attacking_midfielder"
    MIDFIELDER = "midfielder"
    FORWARD = "forward"


class RegistrationStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Player(TimestampMixin, Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    telegram_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True, index=True)

    # Registration fields
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[PlayerPosition] = mapped_column(
        Enum(PlayerPosition, values_callable=lambda e: [m.value for m in e]), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    photo_file_id: Mapped[str] = mapped_column(String(200), nullable=False)

    # Status fields
    role: Mapped[PlayerRole] = mapped_column(
        Enum(PlayerRole, values_callable=lambda e: [m.value for m in e]), nullable=False
    )
    registration_status: Mapped[RegistrationStatus] = mapped_column(
        Enum(RegistrationStatus, values_callable=lambda e: [m.value for m in e]),
        default=RegistrationStatus.PENDING,
    )
    club_id: Mapped[int | None] = mapped_column(ForeignKey("clubs.id"), nullable=True)

    # Current season rating (scraped)
    current_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    division_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    division_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_points_per_game: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Match statistics (scraped from team pages)
    games_played: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mvp_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assists: Mapped[int | None] = mapped_column(Integer, nullable=True)
    yellow_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    red_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Previous season rating (for free agents)
    prev_season_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    prev_division_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prev_division_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prev_position_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prev_position_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prev_avg_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    prev_rating_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    club: Mapped["Club | None"] = relationship(back_populates="players")
