"""
Account repository for data access.
"""

from typing import Optional, List
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from void.data.models import Account, AccountStatus
import structlog

logger = structlog.get_logger()


class AccountRepository:
    """Repository for Account model."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(
        self,
        account_id: UUID,
    ) -> Optional[Account]:
        """Get account by ID."""
        result = await self.db.execute(
            select(Account).where(Account.id == account_id)
        )
        return result.scalar_one_or_none()

    async def get_by_address(
        self,
        address: str,
    ) -> Optional[Account]:
        """Get account by wallet address."""
        result = await self.db.execute(
            select(Account).where(Account.address == address)
        )
        return result.scalar_one_or_none()

    async def get_by_name(
        self,
        name: str,
    ) -> Optional[Account]:
        """Get account by name."""
        result = await self.db.execute(
            select(Account).where(Account.name == name)
        )
        return result.scalar_one_or_none()

    async def list_accounts(
        self,
        status: Optional[AccountStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Account]:
        """List accounts with optional filtering."""
        query = select(Account)

        if status:
            query = query.where(Account.status == status)

        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create(self, account: Account) -> Account:
        """Create new account."""
        self.db.add(account)
        await self.db.flush()
        return account

    async def update(self, account: Account) -> Account:
        """Update existing account."""
        await self.db.flush()
        return account

    async def delete(self, account: Account) -> None:
        """Delete account."""
        await self.db.delete(account)


__all__ = ["AccountRepository"]
