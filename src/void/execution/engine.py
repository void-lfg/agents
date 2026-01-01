"""
Order execution engine.

Submits orders to Polymarket CLOB with retry logic and error handling.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from void.execution.models import OrderRequest, OrderResult, OrderStatus, OrderSide, OrderType
from void.execution.order_manager import OrderManager
from void.data.feeds.polymarket import ClobClientFactory
from void.data.feeds.polymarket.clob_client import ClobClientWrapper
from void.accounts.service import AccountService
from void.data.models import Order as OrderModel
from void.messaging.events import OrderSubmittedEvent, OrderFailedEvent, OrderCancelledEvent
import structlog

logger = structlog.get_logger()


class ExecutionEngine:
    """
    Order execution engine.

    Features:
    - Order submission to Polymarket CLOB
    - Retry logic with exponential backoff
    - Error handling and status tracking
    - Latency measurement
    """

    def __init__(
        self,
        db: AsyncSession,
        account_service: AccountService,
        event_bus: Optional[any] = None,
    ):
        self.db = db
        self.order_manager = OrderManager(db)
        self.account_service = account_service
        self.event_bus = event_bus

        # CLOB client cache
        self._clob_clients: dict[UUID, ClobClientWrapper] = {}

    async def execute_order(
        self,
        request: OrderRequest,
        account_id: UUID,
        max_retries: int = 3,
    ) -> OrderResult:
        """
        Execute order with retry logic.

        Args:
            request: Order request
            account_id: Trading account ID
            max_retries: Maximum retry attempts

        Returns:
            Order execution result
        """
        start_time = datetime.now(timezone.utc)

        try:
            # Create order record
            order = await self.order_manager.create_order(request, account_id)
            await self.db.commit()

            # Get CLOB client
            client = await self._get_clob_client(account_id)

            # Submit order
            for attempt in range(1, max_retries + 1):
                try:
                    if request.order_type == OrderType.FOK or request.order_type == OrderType.FAK:
                        # Market order
                        response = await client.create_market_order(
                            token_id=request.token_id,
                            amount=float(request.price * request.size),
                            side=request.side.value,
                            order_type=request.order_type,
                        )
                    else:
                        # Limit order
                        response = await client.create_order(
                            token_id=request.token_id,
                            price=float(request.price),
                            size=float(request.size),
                            side=request.side.value,
                            order_type=request.order_type,
                        )

                    # Parse response
                    clob_order_id = response.get("orderID") or response.get("id")

                    # Update order
                    await self.order_manager.update_order(
                        order.id,
                        clob_order_id=clob_order_id,
                        status=OrderStatus.SUBMITTED,
                        submitted_at=datetime.now(timezone.utc),
                    )
                    await self.db.commit()

                    # Calculate latency
                    latency_ms = int(
                        (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                    )

                    # Publish event
                    if self.event_bus:
                        await self.event_bus.publish(
                            OrderSubmittedEvent(
                                order_id=order.id,
                                clob_order_id=clob_order_id,
                                market_id=request.market_id,
                                side=request.side.value,
                                price=float(request.price),
                                size=float(request.size),
                                timestamp=datetime.now(timezone.utc),
                            )
                        )

                    logger.info(
                        "order_submitted_successfully",
                        order_id=str(order.id),
                        clob_order_id=clob_order_id,
                        attempt=attempt,
                        latency_ms=latency_ms,
                    )

                    return OrderResult(
                        success=True,
                        order_id=order.id,
                        clob_order_id=clob_order_id,
                        status=OrderStatus.SUBMITTED,
                        latency_ms=latency_ms,
                        attempts=attempt,
                    )

                except Exception as e:
                    error_msg = str(e)
                    logger.warning(
                        "order_submission_failed",
                        order_id=str(order.id),
                        attempt=attempt,
                        error=error_msg,
                    )

                    # Check if should retry
                    if "rate limit" in error_msg.lower():
                        wait_time = 2 ** attempt  # Exponential backoff
                        logger.info(
                            "rate_limited_waiting",
                            order_id=str(order.id),
                            wait_seconds=wait_time,
                        )
                        await asyncio.sleep(wait_time)
                    elif "insufficient" in error_msg.lower():
                        # Don't retry insufficient funds
                        break
                    else:
                        await asyncio.sleep(0.5)

            # All retries failed
            await self.order_manager.update_order(
                order.id,
                status=OrderStatus.REJECTED,
                error_message=f"Failed after {max_retries} attempts",
            )
            await self.db.commit()

            # Publish failure event
            if self.event_bus:
                await self.event_bus.publish(
                    OrderFailedEvent(
                        order_id=order.id,
                        error="Max retries exceeded",
                        timestamp=datetime.now(timezone.utc),
                    )
                )

            return OrderResult(
                success=False,
                order_id=order.id,
                status=OrderStatus.REJECTED,
                error="Max retries exceeded",
                attempts=max_retries,
            )

        except Exception as e:
            logger.error(
                "order_execution_error",
                account_id=str(account_id),
                error=str(e),
            )

            return OrderResult(
                success=False,
                error=str(e),
            )

    async def cancel_order(
        self,
        order_id: UUID,
        account_id: UUID,
    ) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Order ID to cancel
            account_id: Account ID

        Returns:
            True if cancelled successfully
        """
        try:
            # Get order
            order = await self.order_manager.get_order(order_id)
            if not order:
                logger.warning("order_not_found", order_id=str(order_id))
                return False

            # Get CLOB client
            client = await self._get_clob_client(account_id)

            # Cancel on Polymarket
            if order.clob_order_id:
                await client.cancel_order(order.clob_order_id)

            # Update status
            await self.order_manager.update_order(
                order_id,
                status=OrderStatus.CANCELLED,
                cancelled_at=datetime.now(timezone.utc),
            )
            await self.db.commit()

            # Publish event
            if self.event_bus:
                await self.event_bus.publish(
                    OrderCancelledEvent(
                        order_id=order_id,
                        timestamp=datetime.now(timezone.utc),
                    )
                )

            logger.info("order_cancelled", order_id=str(order_id))
            return True

        except Exception as e:
            logger.error(
                "order_cancellation_failed",
                order_id=str(order_id),
                error=str(e),
            )
            return False

    async def cancel_all_orders(
        self,
        account_id: UUID,
    ) -> int:
        """
        Cancel all pending orders for an account.

        Args:
            account_id: Account ID

        Returns:
            Number of orders cancelled
        """
        try:
            # Get CLOB client
            client = await self._get_clob_client(account_id)

            # Cancel all on Polymarket
            response = await client.cancel_all_orders()

            # Mark all as cancelled in DB
            await self.order_manager.cancel_all_pending(account_id)
            await self.db.commit()

            cancelled_count = len(response.get("canceled", []))

            logger.info(
                "all_orders_cancelled",
                account_id=str(account_id),
                count=cancelled_count,
            )

            return cancelled_count

        except Exception as e:
            logger.error(
                "cancel_all_failed",
                account_id=str(account_id),
                error=str(e),
            )
            return 0

    async def _get_clob_client(self, account_id: UUID) -> ClobClientWrapper:
        """
        Get or create CLOB client for account.

        Args:
            account_id: Account ID

        Returns:
            CLOB client wrapper
        """
        # Check cache
        if account_id in self._clob_clients:
            return self._clob_clients[account_id]

        # Get account
        account = await self.account_service.get_account(account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found")

        # Get private key
        private_key = self.account_service.get_private_key(account)

        # Create client
        client = ClobClientFactory.create(
            private_key=private_key,
            address=account.address,
        )

        # Cache it
        self._clob_clients[account_id] = client

        return client


__all__ = ["ExecutionEngine"]
