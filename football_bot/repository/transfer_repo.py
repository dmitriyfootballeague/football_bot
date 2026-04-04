from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from football_bot.models import (
    TransferRequest, TransferStatus, TransferType,
    Player, PlayerRole, RegistrationStatus,
)


class TransferRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _base_query(self):
        return (
            select(TransferRequest)
            .options(
                selectinload(TransferRequest.player),
                selectinload(TransferRequest.from_club),
                selectinload(TransferRequest.to_club),
            )
        )

    async def create(self, request: TransferRequest) -> TransferRequest:
        self.session.add(request)
        await self.session.commit()
        await self.session.refresh(request)
        return request

    async def get_by_id(self, request_id: int) -> TransferRequest | None:
        stmt = self._base_query().where(TransferRequest.id == request_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_for_player(self, player_id: int) -> TransferRequest | None:
        """Check if player has an active (non-terminal) transfer request."""
        active_statuses = [
            TransferStatus.PENDING_CAPTAIN,
            TransferStatus.PENDING_PLAYER_CONFIRM,
            TransferStatus.PENDING_CAPTAIN_CONFIRM,
            TransferStatus.PENDING_ADMIN,
        ]
        stmt = (
            self._base_query()
            .where(
                TransferRequest.player_id == player_id,
                TransferRequest.status.in_(active_statuses),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_pending_for_captain(
        self, club_id: int, transfer_type: TransferType
    ) -> list[TransferRequest]:
        """Get requests awaiting captain action for a specific club."""
        if transfer_type == TransferType.EXIT:
            # EXIT requests from players in this club
            stmt = (
                self._base_query()
                .where(
                    TransferRequest.transfer_type == TransferType.EXIT,
                    TransferRequest.from_club_id == club_id,
                    TransferRequest.status == TransferStatus.PENDING_CAPTAIN,
                )
            )
        elif transfer_type == TransferType.JOIN:
            # JOIN requests targeting this club
            stmt = (
                self._base_query()
                .where(
                    TransferRequest.transfer_type == TransferType.JOIN,
                    TransferRequest.to_club_id == club_id,
                    TransferRequest.status == TransferStatus.PENDING_CAPTAIN,
                )
            )
        elif transfer_type == TransferType.INVITE:
            # INVITE requests where captain needs final confirmation
            stmt = (
                self._base_query()
                .where(
                    TransferRequest.transfer_type == TransferType.INVITE,
                    TransferRequest.to_club_id == club_id,
                    TransferRequest.status == TransferStatus.PENDING_CAPTAIN_CONFIRM,
                )
            )
        else:
            return []
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_invitations_for_player(self, player_id: int) -> list[TransferRequest]:
        """Get pending invitations for a player (FA)."""
        stmt = (
            self._base_query()
            .where(
                TransferRequest.player_id == player_id,
                TransferRequest.transfer_type == TransferType.INVITE,
                TransferRequest.status == TransferStatus.PENDING_PLAYER_CONFIRM,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_confirms_for_player(self, player_id: int) -> list[TransferRequest]:
        """Get JOIN requests where captain approved and player needs to confirm."""
        stmt = (
            self._base_query()
            .where(
                TransferRequest.player_id == player_id,
                TransferRequest.transfer_type == TransferType.JOIN,
                TransferRequest.status == TransferStatus.PENDING_PLAYER_CONFIRM,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_for_admin(self) -> list[TransferRequest]:
        stmt = (
            self._base_query()
            .where(TransferRequest.status == TransferStatus.PENDING_ADMIN)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self, request_id: int, status: TransferStatus, rejected_by: str | None = None
    ) -> None:
        values = {"status": status}
        if rejected_by:
            values["rejected_by"] = rejected_by
        stmt = (
            update(TransferRequest)
            .where(TransferRequest.id == request_id)
            .values(**values)
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def get_free_agents(self) -> list[Player]:
        stmt = (
            select(Player)
            .where(
                Player.role == PlayerRole.FREE_AGENT,
                Player.registration_status == RegistrationStatus.APPROVED,
                Player.is_active == True,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_captain_of_club(self, club_id: int) -> Player | None:
        stmt = (
            select(Player)
            .where(
                Player.club_id == club_id,
                Player.role == PlayerRole.CAPTAIN,
                Player.registration_status == RegistrationStatus.APPROVED,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
