from __future__ import annotations

from sqlalchemy import Enum, Float, Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .player import PlayerPosition
from .base import Base, TimestampMixin


class ScrapedPlayerStats(TimestampMixin, Base):
    """Player statistics scraped from olesports.ru club pages.

    This table stores ALL players from the league site, regardless of
    whether they are registered in the bot. Registered players can be
    linked via Player.external_id matching this table's external_id.
    """
    __tablename__ = "scraped_player_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[PlayerPosition | None] = mapped_column(
        Enum(PlayerPosition, values_callable=lambda e: [m.value for m in e]), nullable=True
    )
    club_id: Mapped[int | None] = mapped_column(ForeignKey("clubs.id"), nullable=True)

    # Match statistics
    games_played: Mapped[int] = mapped_column(Integer, default=0)
    mvp_count: Mapped[int] = mapped_column(Integer, default=0)
    goals: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    yellow_cards: Mapped[int] = mapped_column(Integer, default=0)
    red_cards: Mapped[int] = mapped_column(Integer, default=0)

    # Computed current-season rating fields
    current_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    division_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    division_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_points_per_game: Mapped[float | None] = mapped_column(Float, nullable=True)

    club: Mapped["Club | None"] = relationship(foreign_keys=[club_id])
