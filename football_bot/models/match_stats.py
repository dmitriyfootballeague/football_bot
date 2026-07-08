from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class MatchPlayerStats(TimestampMixin, Base):
    __tablename__ = "match_stats"
    __table_args__ = (
        UniqueConstraint(
            "match_external_id",
            "player_external_id",
            name="uq_match_stats_match_player",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_external_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    match_url: Mapped[str] = mapped_column(String(500), nullable=False)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"), nullable=False)
    club_id: Mapped[int | None] = mapped_column(ForeignKey("clubs.id"), nullable=True)
    season_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    season_label: Mapped[str | None] = mapped_column(String(200), nullable=True)

    player_external_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    player_name: Mapped[str] = mapped_column(String(200), nullable=False)
    team_name: Mapped[str] = mapped_column(String(200), nullable=False)
    opponent_name: Mapped[str] = mapped_column(String(200), nullable=False)
    match_date_label: Mapped[str | None] = mapped_column(String(100), nullable=True)

    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False)
    in_roster: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    started: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mvp: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    team_won: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    team_goals: Mapped[int] = mapped_column(Integer, nullable=False)
    opponent_goals: Mapped[int] = mapped_column(Integer, nullable=False)
    goals_conceded: Mapped[int] = mapped_column(Integer, nullable=False)

    tournament: Mapped["Tournament"] = relationship()
    club: Mapped["Club | None"] = relationship()
