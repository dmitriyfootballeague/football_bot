from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class ScrapedPlayerSeasonStats(TimestampMixin, Base):
    __tablename__ = "scraped_player_season_stats"
    __table_args__ = (
        UniqueConstraint(
            "external_id",
            "season_label",
            name="uq_scraped_player_season_stats_external_id_season_label",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    season_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    season_label: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    season_bucket: Mapped[str] = mapped_column(String(20), nullable=False)
    tournament_name: Mapped[str] = mapped_column(String(200), nullable=False)

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[str | None] = mapped_column(String(100), nullable=True)
    club_id: Mapped[int | None] = mapped_column(ForeignKey("clubs.id"), nullable=True)

    games_played: Mapped[int] = mapped_column(Integer, default=0)
    mvp_count: Mapped[int] = mapped_column(Integer, default=0)
    goals: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    yellow_cards: Mapped[int] = mapped_column(Integer, default=0)
    red_cards: Mapped[int] = mapped_column(Integer, default=0)
    scraped_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_override_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    club: Mapped["Club | None"] = relationship(foreign_keys=[club_id])
