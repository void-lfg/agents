"""
Order lifecycle management.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from void.data.models import Order, Order as OrderModel, OrderStatus
from void.execution.models import OrderRequest, OrderSide, OrderType, OrderResult
import structlog

logger = structlog.get_logger()


class OrderManager:
    """Manages order lifecycle."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_order(
        self,
        request: OrderRequest,
        account_id: UUID,
    ) -> OrderModel:
        """
        Create order record.

        Args:
            request: Order request
            account_id: Trading account ID

        Returns:
            Created order
        """
        order = OrderModel(
            id=uuid4(),
            account_id=account_id,
            market_id=request.market_id,
            signal_id=request.signal_id,
            token_id=request.token_id,
            side=OrderSide[request.side.value.upper()],
            order_type=request.order_type.value,
            price=request.price,
            size=request.size,
            status=OrderStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        self.db.add(order)
        await self.db.flush()

        logger.info(
            "order_created",
            order_id=str(order.id),
            market_id=request.market_id,
            side=request.side.value,
            price=float(request.price),
        )

        return order

    async def update_order(
        self,
        order_id: UUID,
        **kwargs,
    ) -> OrderModel:
        """Update order fields."""
        result = await self.db.execute(
            select(OrderModel).where(OrderModel.id == order_id)
        )
        order = result.scalar_one_or_none()

        if not order:
            raise ValueError(f"Order {order_id} not found")

        for key, value in kwargs.items():
            if hasattr(order, key):
                setattr(order, key, value)

        await self.db.flush()
        return order

    async def get_order(self, order_id: UUID) -> Optional[OrderModel]:
        """Get order by ID."""
        result = await self.db.execute(
            select(OrderModel).where(OrderModel.id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_pending_orders(
        self,
        account_id: UUID,
    ) -> List[OrderModel]:
        """Get all pending orders for account."""
        result = await self.db.execute(
            select(OrderModel).where(
                OrderModel.account_id == account_id,
                OrderModel.status.in_([
                    OrderStatus.PENDING,
                    OrderStatus.SUBMITTED,
                    OrderStatus.PARTIAL,
                ]),
            )
        )
        return list(result.scalars().all())

    async def cancel_all_pending(
        self,
        account_id: UUID,
    ) -> None:
        """Mark all pending orders as cancelled."""
        orders = await self.get_pending_orders(account_id)

        for order in orders:
            order.status = OrderStatus.CANCELLED
            order.cancelled_at = datetime.now(timezone.utc)

        await self.db.flush()

        logger.info(
            "all_pending_orders_cancelled",
            account_id=str(account_id),
            count=len(orders),
        )


__all__ = ["OrderManager"]
