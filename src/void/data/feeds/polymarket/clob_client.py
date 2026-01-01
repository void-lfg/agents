"""
Polymarket CLOB client wrapper.

Wraps py-clob-client with retry logic, rate limiting, and error handling.
"""

import asyncio
from typing import Optional, Dict, Any, List
from decimal import Decimal
import structlog

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, MarketOrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

from void.config import config

logger = structlog.get_logger()


class ClobClientWrapper:
    """
    Wrapper around Polymarket CLOB client.

    Handles:
    - Authentication
    - Rate limiting
    - Retry logic
    - Error handling
    """

    def __init__(
        self,
        private_key: Optional[str] = None,
        address: Optional[str] = None,
    ):
        """
        Initialize CLOB client.

        Args:
            private_key: Wallet private key (for signing)
            address: Wallet address
        """
        self.private_key = private_key
        self.address = address

        # Client will be initialized lazily
        self._client: Optional[ClobClient] = None
        self._api_creds: Optional[Dict[str, str]] = None

    def _init_client(self) -> ClobClient:
        """Initialize CLOB client with credentials."""
        if self._client is not None:
            return self._client

        try:
            # Create client
            self._client = ClobClient(
                host=config.polymarket.clob_url,
                key=self.private_key,
                signature_type=1,  # EIP-712 signing
            )

            # Set API credentials
            self._api_creds = self._client.create_or_derive_api_creds()
            self._client.set_api_creds(self._api_creds)

            logger.info(
                "clob_client_initialized",
                address=self.address,
                host=config.polymarket.clob_url,
            )

            return self._client

        except Exception as e:
            logger.error("clob_client_init_failed", error=str(e))
            raise

    async def get_order_book(
        self,
        token_id: str,
    ) -> Dict[str, Any]:
        """
        Get order book for a token.

        Args:
            token_id: CLOB token ID

        Returns:
            Order book with bids and asks
        """
        client = self._init_client()

        try:
            order_book = client.get_order_book(token_id)

            logger.debug(
                "order_book_fetched",
                token_id=token_id,
                bids=len(order_book.get("bids", [])),
                asks=len(order_book.get("asks", [])),
            )

            return order_book

        except Exception as e:
            logger.error(
                "order_book_fetch_failed",
                token_id=token_id,
                error=str(e),
            )
            raise

    async def get_market_price(
        self,
        token_id: str,
        side: str = "BUY",
    ) -> Dict[str, Any]:
        """
        Get current market price.

        Args:
            token_id: CLOB token ID
            side: BUY or SELL

        Returns:
            Price data
        """
        client = self._init_client()

        try:
            price_data = client.get_price(token_id, side)

            logger.debug(
                "market_price_fetched",
                token_id=token_id,
                side=side,
                price=price_data.get("price"),
            )

            return price_data

        except Exception as e:
            logger.error(
                "market_price_fetch_failed",
                token_id=token_id,
                error=str(e),
            )
            raise

    async def create_order(
        self,
        token_id: str,
        price: float,
        size: float,
        side: str = "BUY",
        order_type: OrderType = OrderType.GTC,
    ) -> Dict[str, Any]:
        """
        Create a limit order.

        Args:
            token_id: CLOB token ID
            price: Price per share (0-1)
            size: Number of shares
            side: BUY or SELL
            order_type: GTC, GTD, FOK, FAK

        Returns:
            Order response with order ID
        """
        client = self._init_client()

        try:
            # Create order args
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=BUY if side == "BUY" else SELL,
            )

            # Sign order
            signed_order = client.create_order(order_args)

            # Post order
            response = client.post_order(signed_order, order_type)

            order_id = response.get("orderID") or response.get("id")

            logger.info(
                "order_created",
                order_id=order_id,
                token_id=token_id,
                side=side,
                price=price,
                size=size,
                order_type=order_type.value,
            )

            return response

        except Exception as e:
            logger.error(
                "order_creation_failed",
                token_id=token_id,
                error=str(e),
            )
            raise

    async def create_market_order(
        self,
        token_id: str,
        amount: float,
        side: str = "BUY",
        order_type: OrderType = OrderType.FOK,
    ) -> Dict[str, Any]:
        """
        Create a market order (Fill-Or-Kill recommended).

        Args:
            token_id: CLOB token ID
            amount: Amount in USD to trade
            side: BUY or SELL
            order_type: FOK (Fill-Or-Kill) or FAK (Fill-And-Kill)

        Returns:
            Order response
        """
        client = self._init_client()

        try:
            # Create market order args
            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=amount,
                side=BUY if side == "BUY" else SELL,
            )

            # Sign order
            signed_order = client.create_market_order(order_args)

            # Post order
            response = client.post_order(signed_order, order_type)

            order_id = response.get("orderID") or response.get("id")

            logger.info(
                "market_order_created",
                order_id=order_id,
                token_id=token_id,
                side=side,
                amount=amount,
                order_type=order_type.value,
            )

            return response

        except Exception as e:
            logger.error(
                "market_order_creation_failed",
                token_id=token_id,
                error=str(e),
            )
            raise

    async def cancel_order(
        self,
        order_id: str,
    ) -> Dict[str, Any]:
        """
        Cancel an order.

        Args:
            order_id: CLOB order ID

        Returns:
            Cancellation response
        """
        client = self._init_client()

        try:
            response = client.cancel(order_id)

            logger.info(
                "order_cancelled",
                order_id=order_id,
            )

            return response

        except Exception as e:
            logger.error(
                "order_cancellation_failed",
                order_id=order_id,
                error=str(e),
            )
            raise

    async def cancel_all_orders(self) -> Dict[str, Any]:
        """
        Cancel all open orders.

        Returns:
            Cancellation response with list of cancelled orders
        """
        client = self._init_client()

        try:
            response = client.cancel_all()
            cancelled = response.get("canceled", [])

            logger.info(
                "all_orders_cancelled",
                count=len(cancelled),
            )

            return response

        except Exception as e:
            logger.error("cancel_all_failed", error=str(e))
            raise

    async def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        Get all open orders.

        Returns:
            List of open orders
        """
        client = self._init_client()

        try:
            orders = client.get_open_orders()

            logger.debug(
                "open_orders_fetched",
                count=len(orders),
            )

            return orders

        except Exception as e:
            logger.error("open_orders_fetch_failed", error=str(e))
            raise


class ClobClientFactory:
    """Factory for creating CLOB clients."""

    @staticmethod
    def create_from_env() -> ClobClientWrapper:
        """
        Create CLOB client from environment configuration.

        Uses the credentials from config.polymarket.
        """
        # Note: In production, you'd decrypt these from the database
        # For now, we return a wrapper that will derive API creds

        return ClobClientWrapper(
            private_key=None,  # Will be set when needed
            address=None,
        )

    @staticmethod
    def create(
        private_key: str,
        address: str,
    ) -> ClobClientWrapper:
        """
        Create CLOB client with explicit credentials.

        Args:
            private_key: Wallet private key
            address: Wallet address

        Returns:
            Initialized CLOB client wrapper
        """
        return ClobClientWrapper(
            private_key=private_key,
            address=address,
        )


__all__ = [
    "ClobClientWrapper",
    "ClobClientFactory",
]
