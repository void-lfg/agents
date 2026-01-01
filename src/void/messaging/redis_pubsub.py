"""
Redis pub/sub implementation for event bus.
"""

import json
import asyncio
from typing import Callable, Dict, List, Optional
from redis.asyncio import Redis, ConnectionPool
import structlog

from void.config import config
from void.messaging.events import BaseEvent, EventType

logger = structlog.get_logger()


class RedisPubSub:
    """
    Redis pub/sub for event distribution.

    Usage:
        pubsub = RedisPubSub()

        # Subscribe to events
        await pubsub.subscribe(EventType.SIGNAL_DETECTED, my_handler)

        # Publish events
        await pubsub.publish(EventType.SIGNAL_DETECTED, {...data...})
    """

    def __init__(self):
        # Create connection pool
        self.pool = ConnectionPool.from_url(
            str(config.redis.url),
            max_connections=config.redis.max_connections,
            decode_responses=True,
        )

        # Redis clients
        self.redis: Optional[Redis] = None
        self.pubsub = None

        # Event handlers
        self._handlers: Dict[EventType, List[Callable]] = {}
        self._listener_task: Optional[asyncio.Task] = None

        # Channel prefix
        self.channel_prefix = "void:events"

    async def connect(self) -> None:
        """Connect to Redis."""
        self.redis = Redis(connection_pool=self.pool)
        self.pubsub = self.redis.pubsub()

        # Start listener task
        self._listener_task = asyncio.create_task(self._listen_loop())

        logger.info("redis_connected", url=str(config.redis.url))

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self.pubsub:
            await self.pubsub.close()

        if self.redis:
            await self.redis.close()

        await self.pool.disconnect()

        logger.info("redis_disconnected")

    async def publish(
        self,
        event_type: EventType,
        data: dict,
    ) -> None:
        """
        Publish an event to Redis.

        Args:
            event_type: Type of event
            data: Event data (will be JSON serialized)
        """
        if not self.redis:
            raise RuntimeError("Redis not connected. Call connect() first.")

        channel = f"{self.channel_prefix}:{event_type.value}"
        message = json.dumps(data)

        await self.redis.publish(channel, message)

        logger.debug(
            "event_published",
            event_type=event_type.value,
            channel=channel,
        )

    async def subscribe(
        self,
        event_type: EventType,
        handler: Callable,
    ) -> None:
        """
        Subscribe to an event type.

        Args:
            event_type: Type of event to subscribe to
            handler: Async callback function(event_data)
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []

        self._handlers[event_type].append(handler)

        # Subscribe to Redis channel
        channel = f"{self.channel_prefix}:{event_type.value}"
        await self.pubsub.subscribe(channel)

        logger.debug(
            "event_subscribed",
            event_type=event_type.value,
            handler=handler.__name__,
        )

    async def unsubscribe(
        self,
        event_type: EventType,
        handler: Callable,
    ) -> None:
        """Unsubscribe handler from event type."""
        if event_type in self._handlers:
            self._handlers[event_type].remove(handler)

            # If no more handlers, unsubscribe from channel
            if not self._handlers[event_type]:
                channel = f"{self.channel_prefix}:{event_type.value}"
                await self.pubsub.unsubscribe(channel)
                del self._handlers[event_type]

            logger.debug(
                "event_unsubscribed",
                event_type=event_type.value,
                handler=handler.__name__,
            )

    async def _listen_loop(self) -> None:
        """Listen for incoming messages."""
        logger.info("redis_listener_started")

        try:
            async for message in self.pubsub.listen():
                if message["type"] == "message":
                    await self._handle_message(message)

        except asyncio.CancelledError:
            logger.info("redis_listener_cancelled")
            raise

        except Exception as e:
            logger.error("redis_listener_error", error=str(e))
            raise

    async def _handle_message(self, message: dict) -> None:
        """Handle incoming message."""
        try:
            # Extract channel and data
            channel = message["channel"]
            data_str = message["data"]

            # Parse event type from channel
            event_type_str = channel.replace(f"{self.channel_prefix}:", "")
            event_type = EventType(event_type_str)

            # Parse JSON data
            data = json.loads(data_str)

            # Call all handlers for this event type
            if event_type in self._handlers:
                for handler in self._handlers[event_type]:
                    try:
                        # Call handler
                        if asyncio.iscoroutinefunction(handler):
                            await handler(data)
                        else:
                            handler(data)

                    except Exception as e:
                        logger.error(
                            "event_handler_error",
                            event_type=event_type.value,
                            handler=handler.__name__,
                            error=str(e),
                        )

        except Exception as e:
            logger.error("message_handle_error", error=str(e))


class EventBus:
    """
    High-level event bus for VOID system.

    Wraps Redis pub/sub with type-safe event publishing.
    """

    def __init__(self):
        self.pubsub = RedisPubSub()
        self._connected = False

    async def connect(self) -> None:
        """Connect to event bus."""
        await self.pubsub.connect()
        self._connected = True
        logger.info("event_bus_connected")

    async def disconnect(self) -> None:
        """Disconnect from event bus."""
        await self.pubsub.disconnect()
        self._connected = False
        logger.info("event_bus_disconnected")

    async def publish(self, event: BaseEvent) -> None:
        """
        Publish an event.

        Args:
            event: Event instance to publish
        """
        if not self._connected:
            raise RuntimeError("Event bus not connected. Call connect() first.")

        await self.pubsub.publish(
            event_type=event.event_type,
            data=event.to_dict(),
        )

    async def subscribe(
        self,
        event_type: EventType,
        handler: Callable,
    ) -> None:
        """
        Subscribe to an event type.

        Args:
            event_type: Type of event to subscribe to
            handler: Callback function(event_data)
        """
        await self.pubsub.subscribe(event_type, handler)

    async def unsubscribe(
        self,
        event_type: EventType,
        handler: Callable,
    ) -> None:
        """Unsubscribe from event type."""
        await self.pubsub.unsubscribe(event_type, handler)


__all__ = ["RedisPubSub", "EventBus"]
