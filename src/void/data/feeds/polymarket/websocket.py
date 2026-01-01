"""
Polymarket WebSocket client for real-time market data.

Subscribes to market updates and price changes.
"""

import json
import asyncio
from typing import Callable, Dict, List, Optional, Set
import websockets
import structlog

from void.config import config

logger = structlog.get_logger()


class PolymarketWebSocket:
    """
    WebSocket client for real-time Polymarket data.

    Subscribes to:
    - Price changes
    - Order book updates
    - Trade events
    """

    def __init__(self):
        self.ws_url = config.polymarket.ws_url
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._subscribed_assets: Set[str] = set()
        self._callbacks: Dict[str, List[Callable]] = {}
        self._listen_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """Connect to WebSocket server."""
        try:
            self._ws = await websockets.connect(
                self.ws_url,
                ping_interval=30,
                ping_timeout=10,
            )

            self._running = True
            self._listen_task = asyncio.create_task(self._listen_loop())

            logger.info("websocket_connected", url=self.ws_url)

        except Exception as e:
            logger.error("websocket_connect_failed", error=str(e))
            raise

    async def disconnect(self) -> None:
        """Disconnect from WebSocket server."""
        self._running = False

        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass

        if self._ws:
            await self._ws.close()

        logger.info("websocket_disconnected")

    async def subscribe_to_markets(
        self,
        market_ids: List[str],
        callback: Callable[[Dict], None],
    ) -> None:
        """
        Subscribe to market updates.

        Args:
            market_ids: List of market/token IDs to subscribe to
            callback: Async callback function for market data
        """
        if not self._ws:
            await self.connect()

        # Build subscription message
        message = {
            "type": "market",
            "markets": market_ids,
            "assets_ids": market_ids,
        }

        try:
            await self._ws.send(json.dumps(message))

            # Register callbacks
            for market_id in market_ids:
                self._subscribed_assets.add(market_id)

                if market_id not in self._callbacks:
                    self._callbacks[market_id] = []

                self._callbacks[market_id].append(callback)

            logger.info(
                "websocket_subscribed",
                markets=len(market_ids),
            )

        except Exception as e:
            logger.error(
                "websocket_subscribe_failed",
                error=str(e),
            )
            raise

    async def unsubscribe_from_markets(
        self,
        market_ids: List[str],
    ) -> None:
        """
        Unsubscribe from market updates.

        Args:
            market_ids: List of market IDs to unsubscribe from
        """
        # Remove callbacks
        for market_id in market_ids:
            if market_id in self._callbacks:
                del self._callbacks[market_id]

            self._subscribed_assets.discard(market_id)

        logger.info(
            "websocket_unsubscribed",
            markets=len(market_ids),
        )

    async def _listen_loop(self) -> None:
        """Main listening loop for WebSocket messages."""
        logger.info("websocket_listener_started")

        try:
            while self._running:
                try:
                    # Receive message with timeout
                    message = await asyncio.wait_for(
                        self._ws.recv(),
                        timeout=60.0,
                    )

                    # Parse and handle message
                    data = json.loads(message)
                    await self._handle_message(data)

                except asyncio.TimeoutError:
                    # Send ping to keep connection alive
                    if self._ws:
                        try:
                            await self._ws.ping()
                        except Exception:
                            logger.warning("websocket_ping_failed")
                            await self._reconnect()

                except websockets.ConnectionClosed:
                    logger.warning("websocket_connection_closed")
                    await self._reconnect()

        except asyncio.CancelledError:
            logger.info("websocket_listener_cancelled")
            raise

        except Exception as e:
            logger.error("websocket_listener_error", error=str(e))
            raise

    async def _handle_message(self, data: Dict) -> None:
        """
        Handle incoming WebSocket message.

        Args:
            data: Parsed JSON message
        """
        try:
            # Extract event type
            event_type = data.get("event_type")
            asset_id = data.get("asset_id")

            if not asset_id:
                return

            # Route to callbacks
            if asset_id in self._callbacks:
                for callback in self._callbacks[asset_id]:
                    try:
                        # Call callback
                        if asyncio.iscoroutinefunction(callback):
                            await callback(data)
                        else:
                            callback(data)

                    except Exception as e:
                        logger.error(
                            "websocket_callback_error",
                            asset_id=asset_id,
                            error=str(e),
                        )

        except Exception as e:
            logger.error("message_handle_error", error=str(e))

    async def _reconnect(self) -> None:
        """Attempt to reconnect to WebSocket."""
        logger.info("websocket_reconnecting")

        await asyncio.sleep(5)

        try:
            await self.disconnect()
            await self.connect()

            # Resubscribe to all assets
            if self._subscribed_assets:
                for asset_id, callbacks in self._callbacks.items():
                    for callback in callbacks:
                        await self.subscribe_to_markets(
                            [asset_id],
                            callback,
                        )

            logger.info("websocket_reconnected")

        except Exception as e:
            logger.error("websocket_reconnect_failed", error=str(e))


class MarketDataCache:
    """
    Cache for real-time market data from WebSocket.

    Provides in-memory storage of latest market data.
    """

    def __init__(self):
        self._cache: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()

    async def update(self, market_id: str, data: Dict) -> None:
        """
        Update cached market data.

        Args:
            market_id: Market ID
            data: Market data update
        """
        async with self._lock:
            # Merge update with existing cache
            if market_id in self._cache:
                self._cache[market_id].update(data)
            else:
                self._cache[market_id] = data.copy()

    async def get(self, market_id: str) -> Optional[Dict]:
        """
        Get cached market data.

        Args:
            market_id: Market ID

        Returns:
            Cached market data or None
        """
        async with self._lock:
            return self._cache.get(market_id)

    async def get_all(self) -> Dict[str, Dict]:
        """
        Get all cached market data.

        Returns:
            Dict of all cached markets
        """
        async with self._lock:
            return self._cache.copy()

    async def clear(self) -> None:
        """Clear all cached data."""
        async with self._lock:
            self._cache.clear()


__all__ = [
    "PolymarketWebSocket",
    "MarketDataCache",
]
