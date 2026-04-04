from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from football_bot.models import (
    Player, PlayerRole, TransferRequest, TransferType, TransferStatus,
)
from football_bot.repository import PlayerRepository, TransferRepository


class TransferService:
    def __init__(self, session: AsyncSession):
        self.repo = TransferRepository(session)
        self.player_repo = PlayerRepository(session)
        self.session = session

    # --- Creation ---

    async def create_exit_request(self, player: Player) -> TransferRequest:
        request = TransferRequest(
            player_id=player.id,
            transfer_type=TransferType.EXIT,
            status=TransferStatus.PENDING_CAPTAIN,
            from_club_id=player.club_id,
            to_club_id=None,
            initiated_by=player.telegram_id,
        )
        return await self.repo.create(request)

    async def create_join_request(
        self, player: Player, to_club_id: int
    ) -> TransferRequest:
        request = TransferRequest(
            player_id=player.id,
            transfer_type=TransferType.JOIN,
            status=TransferStatus.PENDING_CAPTAIN,
            from_club_id=player.club_id,
            to_club_id=to_club_id,
            initiated_by=player.telegram_id,
        )
        return await self.repo.create(request)

    async def create_kick_request(
        self, captain: Player, target_player_id: int
    ) -> TransferRequest:
        """Captain force-kicks a player; goes directly to admin for approval."""
        request = TransferRequest(
            player_id=target_player_id,
            transfer_type=TransferType.KICK,
            status=TransferStatus.PENDING_ADMIN,
            from_club_id=captain.club_id,
            to_club_id=None,
            initiated_by=captain.telegram_id,
        )
        return await self.repo.create(request)

    async def get_club_players(self, club_id: int, exclude_captain_id: int) -> list[Player]:
        """Return all non-captain approved players in the club."""
        from sqlalchemy import select
        from football_bot.models import RegistrationStatus
        stmt = (
            select(Player)
            .where(
                Player.club_id == club_id,
                Player.role == PlayerRole.PLAYER,
                Player.id != exclude_captain_id,
                Player.registration_status == RegistrationStatus.APPROVED,
                Player.is_active == True,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_invite(
        self, captain: Player, player_id: int, club_id: int
    ) -> TransferRequest:
        request = TransferRequest(
            player_id=player_id,
            transfer_type=TransferType.INVITE,
            status=TransferStatus.PENDING_PLAYER_CONFIRM,
            from_club_id=None,
            to_club_id=club_id,
            initiated_by=captain.telegram_id,
        )
        return await self.repo.create(request)

    # --- Captain decisions ---

    async def captain_approve(self, request_id: int) -> TransferRequest:
        req = await self.repo.get_by_id(request_id)
        if req.transfer_type == TransferType.EXIT:
            await self.repo.update_status(request_id, TransferStatus.PENDING_ADMIN)
        elif req.transfer_type == TransferType.JOIN:
            await self.repo.update_status(request_id, TransferStatus.PENDING_PLAYER_CONFIRM)
        return await self.repo.get_by_id(request_id)

    async def captain_reject(self, request_id: int) -> TransferRequest:
        await self.repo.update_status(request_id, TransferStatus.REJECTED, rejected_by="captain")
        return await self.repo.get_by_id(request_id)

    async def captain_confirm_invite(self, request_id: int) -> TransferRequest:
        """Captain final confirmation after FA accepted invite."""
        await self.repo.update_status(request_id, TransferStatus.PENDING_ADMIN)
        return await self.repo.get_by_id(request_id)

    # --- Player decisions ---

    async def player_confirm_join(self, request_id: int) -> TransferRequest:
        """Player confirms JOIN after captain approved."""
        await self.repo.update_status(request_id, TransferStatus.PENDING_ADMIN)
        return await self.repo.get_by_id(request_id)

    async def player_accept_invite(self, request_id: int) -> TransferRequest:
        """FA accepts invitation → awaiting captain final confirmation."""
        await self.repo.update_status(request_id, TransferStatus.PENDING_CAPTAIN_CONFIRM)
        return await self.repo.get_by_id(request_id)

    async def player_reject_invite(self, request_id: int) -> TransferRequest:
        await self.repo.update_status(request_id, TransferStatus.REJECTED, rejected_by="player")
        return await self.repo.get_by_id(request_id)

    # --- Admin decisions ---

    async def admin_approve(self, request_id: int) -> TransferRequest:
        req = await self.repo.get_by_id(request_id)
        await self.repo.update_status(request_id, TransferStatus.APPROVED)

        # Apply the transfer: update player's club and role
        if req.transfer_type in (TransferType.EXIT, TransferType.KICK):
            stmt = (
                update(Player)
                .where(Player.id == req.player_id)
                .values(club_id=None, role=PlayerRole.FREE_AGENT)
            )
            await self.session.execute(stmt)
            await self.session.commit()
        elif req.transfer_type in (TransferType.JOIN, TransferType.INVITE):
            stmt = (
                update(Player)
                .where(Player.id == req.player_id)
                .values(club_id=req.to_club_id, role=PlayerRole.PLAYER)
            )
            await self.session.execute(stmt)
            await self.session.commit()

        return await self.repo.get_by_id(request_id)

    async def admin_reject(self, request_id: int) -> TransferRequest:
        await self.repo.update_status(request_id, TransferStatus.REJECTED, rejected_by="admin")
        return await self.repo.get_by_id(request_id)

    # --- Queries ---

    async def get_request(self, request_id: int) -> TransferRequest | None:
        return await self.repo.get_by_id(request_id)

    async def get_active_for_player(self, player_id: int) -> TransferRequest | None:
        return await self.repo.get_active_for_player(player_id)

    async def get_free_agents(self) -> list[Player]:
        return await self.repo.get_free_agents()

    async def get_captain_of_club(self, club_id: int) -> Player | None:
        return await self.repo.get_captain_of_club(club_id)

    async def get_exit_requests_for_captain(self, club_id: int) -> list[TransferRequest]:
        return await self.repo.get_pending_for_captain(club_id, TransferType.EXIT)

    async def get_join_requests_for_captain(self, club_id: int) -> list[TransferRequest]:
        return await self.repo.get_pending_for_captain(club_id, TransferType.JOIN)

    async def get_invite_confirms_for_captain(self, club_id: int) -> list[TransferRequest]:
        return await self.repo.get_pending_for_captain(club_id, TransferType.INVITE)

    async def get_invitations_for_player(self, player_id: int) -> list[TransferRequest]:
        return await self.repo.get_invitations_for_player(player_id)

    async def get_pending_confirms_for_player(self, player_id: int) -> list[TransferRequest]:
        return await self.repo.get_pending_confirms_for_player(player_id)

    async def get_player_by_telegram_id(self, telegram_id: int) -> Player | None:
        return await self.player_repo.get_by_telegram_id(telegram_id)
