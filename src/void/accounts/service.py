"""
Account management service.

Handles account CRUD, wallet operations, and balance tracking.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from void.accounts.repository import AccountRepository
from void.accounts.encryption import KeyEncryption
from void.accounts.wallet import WalletOperations
from void.data.models import Account, AccountStatus
from void.config import config

import structlog

logger = structlog.get_logger()


class AccountService:
    """Service for managing trading accounts."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AccountRepository(db)
        self.encryption = KeyEncryption()
        self.wallet_ops = WalletOperations()

    async def create_account(
        self,
        name: str,
        telegram_user_id: int,
        private_key: Optional[str] = None,
    ) -> Account:
        """
        Create a new trading account.

        Args:
            name: Account name
            telegram_user_id: Telegram user ID who owns this account
            private_key: Optional private key (generated if not provided)

        Returns:
            Created account
        """
        # Check if name already exists for this user
        from sqlalchemy import select
        result = await self.db.execute(
            select(Account).where(
                Account.telegram_user_id == telegram_user_id,
                Account.name == name
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise ValueError(f"Account with name '{name}' already exists for this user")

        # Generate or use provided private key
        if not private_key:
            private_key = self.wallet_ops.generate_private_key()

        # Get address
        address = self.wallet_ops.get_address(private_key)

        # Encrypt private key
        encrypted_key = self.encryption.encrypt(private_key)

        # Create account
        account = Account(
            telegram_user_id=telegram_user_id,
            name=name,
            address=address,
            encrypted_private_key=encrypted_key,
            key_provider="local",
            status=AccountStatus.ACTIVE,
        )

        # Save to database
        account = await self.repo.create(account)
        await self.db.commit()
        await self.db.refresh(account)

        logger.info(
            "account_created",
            account_id=str(account.id),
            telegram_user_id=telegram_user_id,
            name=name,
            address=address,
        )

        return account

    async def get_account(
        self,
        account_id: UUID,
    ) -> Optional[Account]:
        """Get account by ID."""
        return await self.repo.get_by_id(account_id)

    async def get_account_by_address(
        self,
        address: str,
    ) -> Optional[Account]:
        """Get account by wallet address."""
        return await self.repo.get_by_address(address)

    async def list_accounts(
        self,
        status: Optional[AccountStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Account]:
        """List accounts with optional filtering."""
        return await self.repo.list_accounts(
            status=status,
            limit=limit,
            offset=offset,
        )

    async def sync_balances(
        self,
        account_id: UUID,
    ) -> Account:
        """
        Sync on-chain balances for an account.

        Args:
            account_id: Account ID

        Returns:
            Updated account
        """
        account = await self.get_account(account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found")

        # Get balances from blockchain
        usdc_balance = await self.wallet_ops.get_usdc_balance(account.address)
        matic_balance = await self.wallet_ops.get_matic_balance(account.address)

        # Update account
        account.usdc_balance = usdc_balance
        account.matic_balance = matic_balance
        account.last_synced_at = datetime.utcnow()

        # Save
        account = await self.repo.update(account)
        await self.db.commit()
        await self.db.refresh(account)

        logger.info(
            "balances_synced",
            account_id=str(account_id),
            usdc=float(usdc_balance),
            matic=float(matic_balance),
        )

        return account

    def get_private_key(
        self,
        account: Account,
    ) -> str:
        """
        Decrypt and return private key for account.

        Args:
            account: Account object

        Returns:
            Decrypted private key
        """
        try:
            return self.encryption.decrypt(account.encrypted_private_key)
        except Exception as e:
            logger.error(
                "private_key_decrypt_failed",
                account_id=str(account.id),
                error=str(e),
            )
            raise

    async def disable_account(
        self,
        account_id: UUID,
    ) -> Account:
        """Disable an account (prevents new trading)."""
        account = await self.get_account(account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found")

        account.status = AccountStatus.DISABLED

        account = await self.repo.update(account)
        await self.db.commit()
        await self.db.refresh(account)

        logger.info("account_disabled", account_id=str(account_id))

        return account

    async def delete_account(
        self,
        account_id: UUID,
    ) -> None:
        """
        Delete an account permanently.

        WARNING: This is irreversible! All account data will be lost.
        Make sure user has backed up private key before calling this.

        Args:
            account_id: Account ID to delete
        """
        account = await self.get_account(account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found")

        # Check for associated agents and delete them first
        from sqlalchemy import select
        from void.data.models import Agent

        result = await self.db.execute(
            select(Agent).where(Agent.account_id == account_id)
        )
        agents = result.scalars().all()

        if agents:
            logger.info(
                "deleting_associated_agents",
                account_id=str(account_id),
                agent_count=len(agents)
            )
            for agent in agents:
                await self.db.delete(agent)

        # Delete positions associated with this account
        from void.data.models import Position
        result = await self.db.execute(
            select(Position).where(Position.account_id == account_id)
        )
        positions = result.scalars().all()

        if positions:
            logger.info(
                "deleting_associated_positions",
                account_id=str(account_id),
                position_count=len(positions)
            )
            for position in positions:
                await self.db.delete(position)

        # Now delete the account
        await self.repo.delete(account)
        await self.db.commit()

        logger.info(
            "account_deleted",
            account_id=str(account_id),
            name=account.name,
            address=account.address,
            agents_deleted=len(agents),
            positions_deleted=len(positions),
        )


__all__ = ["AccountService"]
