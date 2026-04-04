from __future__ import annotations

import enum

from sqlalchemy import BigInteger, Integer, String, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class TransferType(str, enum.Enum):
    EXIT = "exit"       # Player leaving club → free agent
    JOIN = "join"       # Player/FA requesting to join club
    INVITE = "invite"   # Captain inviting FA to club
    KICK = "kick"       # Captain force-removing a player


class TransferStatus(str, enum.Enum):
    PENDING_CAPTAIN = "pending_captain"
    PENDING_PLAYER_CONFIRM = "pending_player"
    PENDING_CAPTAIN_CONFIRM = "pending_captain_confirm"
    PENDING_ADMIN = "pending_admin"
    APPROVED = "approved"
    REJECTED = "rejected"


class TransferRequest(TimestampMixin, Base):
    __tablename__ = "transfer_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)
    transfer_type: Mapped[TransferType] = mapped_column(
        Enum(TransferType, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    status: Mapped[TransferStatus] = mapped_column(
        Enum(TransferStatus, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    from_club_id: Mapped[int | None] = mapped_column(ForeignKey("clubs.id"), nullable=True)
    to_club_id: Mapped[int | None] = mapped_column(ForeignKey("clubs.id"), nullable=True)
    initiated_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rejected_by: Mapped[str | None] = mapped_column(String(50), nullable=True)

    player: Mapped["Player"] = relationship(foreign_keys=[player_id])
    from_club: Mapped["Club | None"] = relationship(foreign_keys=[from_club_id])
    to_club: Mapped["Club | None"] = relationship(foreign_keys=[to_club_id])
