"""
Event definitions for the message bus.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID
from enum import Enum


class EventType(str, Enum):
    """Event types."""

    # Agent lifecycle events
    AGENT_STARTED = "agent.started"
    AGENT_STOPPED = "agent.stopped"
    AGENT_PAUSED = "agent.paused"
    AGENT_RESUMED = "agent.resumed"
    AGENT_ERROR = "agent.error"

    # Signal events
    SIGNAL_DETECTED = "signal.detected"
    SIGNAL_VERIFIED = "signal.verified"
    SIGNAL_EXECUTED = "signal.executed"
    SIGNAL_EXPIRED = "signal.expired"
    SIGNAL_REJECTED = "signal.rejected"

    # Order events
    ORDER_SUBMITTED = "order.submitted"
    ORDER_FILLED = "order.filled"
    ORDER_PARTIAL_FILLED = "order.partial_filled"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_REJECTED = "order.rejected"
    ORDER_EXPIRED = "order.expired"

    # Market events
    MARKET_UPDATED = "market.updated"
    MARKET_CLOSED = "market.closed"
    MARKET_RESOLVED = "market.resolved"

    # Position events
    POSITION_OPENED = "position.opened"
    POSITION_CLOSED = "position.closed"
    POSITION_UPDATED = "position.updated"

    # System events
    SYSTEM_ERROR = "system.error"
    SYSTEM_WARNING = "system.warning"
    SYSTEM_INFO = "system.info"


@dataclass
class BaseEvent:
    """Base event class."""

    event_type: EventType
    timestamp: datetime
    data: Dict[str, Any]

    def __init__(self, event_type: EventType, data: Dict[str, Any]):
        self.event_type = event_type
        self.timestamp = datetime.now(timezone.utc)
        self.data = data

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
        }


# ============== AGENT EVENTS ==============

@dataclass
class AgentStartedEvent(BaseEvent):
    """Event fired when agent starts."""

    def __init__(self, agent_id: UUID, strategy: str, timestamp: datetime):
        super().__init__(
            event_type=EventType.AGENT_STARTED,
            data={
                "agent_id": str(agent_id),
                "strategy": strategy,
            },
        )
        self.timestamp = timestamp


@dataclass
class AgentStoppedEvent(BaseEvent):
    """Event fired when agent stops."""

    def __init__(self, agent_id: UUID, timestamp: datetime):
        super().__init__(
            event_type=EventType.AGENT_STOPPED,
            data={"agent_id": str(agent_id)},
        )
        self.timestamp = timestamp


@dataclass
class AgentErrorEvent(BaseEvent):
    """Event fired when agent encounters error."""

    def __init__(self, agent_id: UUID, error: str, timestamp: datetime):
        super().__init__(
            event_type=EventType.AGENT_ERROR,
            data={
                "agent_id": str(agent_id),
                "error": error,
            },
        )
        self.timestamp = timestamp


# ============== SIGNAL EVENTS ==============

@dataclass
class SignalDetectedEvent(BaseEvent):
    """Event fired when signal is detected."""

    def __init__(
        self,
        signal_id: UUID,
        agent_id: UUID,
        market_id: str,
        strategy_type: str,
        predicted_outcome: str,
        entry_price: float,
        profit_margin: float,
    ):
        super().__init__(
            event_type=EventType.SIGNAL_DETECTED,
            data={
                "signal_id": str(signal_id),
                "agent_id": str(agent_id),
                "market_id": market_id,
                "strategy_type": strategy_type,
                "predicted_outcome": predicted_outcome,
                "entry_price": entry_price,
                "profit_margin": profit_margin,
            },
        )


@dataclass
class SignalVerifiedEvent(BaseEvent):
    """Event fired when signal is verified."""

    def __init__(
        self,
        signal_id: UUID,
        confidence: float,
        verification_source: str,
    ):
        super().__init__(
            event_type=EventType.SIGNAL_VERIFIED,
            data={
                "signal_id": str(signal_id),
                "confidence": float(confidence),
                "verification_source": verification_source,
            },
        )


# ============== ORDER EVENTS ==============

@dataclass
class OrderSubmittedEvent(BaseEvent):
    """Event fired when order is submitted."""

    def __init__(
        self,
        order_id: UUID,
        clob_order_id: str,
        market_id: str,
        side: str,
        price: float,
        size: float,
        timestamp: datetime,
    ):
        super().__init__(
            event_type=EventType.ORDER_SUBMITTED,
            data={
                "order_id": str(order_id),
                "clob_order_id": clob_order_id,
                "market_id": market_id,
                "side": side,
                "price": price,
                "size": size,
            },
        )
        self.timestamp = timestamp


@dataclass
class OrderFilledEvent(BaseEvent):
    """Event fired when order is filled."""

    def __init__(
        self,
        order_id: UUID,
        fill_price: float,
        fill_size: float,
        fee: float,
    ):
        super().__init__(
            event_type=EventType.ORDER_FILLED,
            data={
                "order_id": str(order_id),
                "fill_price": fill_price,
                "fill_size": fill_size,
                "fee": fee,
            },
        )


@dataclass
class OrderFailedEvent(BaseEvent):
    """Event fired when order fails."""

    def __init__(self, order_id: UUID, error: str, timestamp: datetime):
        super().__init__(
            event_type=EventType.ORDER_REJECTED,
            data={
                "order_id": str(order_id),
                "error": error,
            },
        )
        self.timestamp = timestamp


@dataclass
class OrderCancelledEvent(BaseEvent):
    """Event fired when order is cancelled."""

    def __init__(self, order_id: UUID, timestamp: datetime):
        super().__init__(
            event_type=EventType.ORDER_CANCELLED,
            data={"order_id": str(order_id)},
        )
        self.timestamp = timestamp


# ============== MARKET EVENTS ==============

@dataclass
class MarketUpdatedEvent(BaseEvent):
    """Event fired when market data is updated."""

    def __init__(
        self,
        market_id: str,
        yes_price: float,
        no_price: float,
        volume: float,
    ):
        super().__init__(
            event_type=EventType.MARKET_UPDATED,
            data={
                "market_id": market_id,
                "yes_price": yes_price,
                "no_price": no_price,
                "volume": volume,
            },
        )


@dataclass
class MarketResolvedEvent(BaseEvent):
    """Event fired when market is resolved."""

    def __init__(
        self,
        market_id: str,
        outcome: str,
        resolution_price: float,
    ):
        super().__init__(
            event_type=EventType.MARKET_RESOLVED,
            data={
                "market_id": market_id,
                "outcome": outcome,
                "resolution_price": resolution_price,
            },
        )


__all__ = [
    "EventType",
    "BaseEvent",
    "AgentStartedEvent",
    "AgentStoppedEvent",
    "AgentErrorEvent",
    "SignalDetectedEvent",
    "SignalVerifiedEvent",
    "OrderSubmittedEvent",
    "OrderFilledEvent",
    "OrderFailedEvent",
    "OrderCancelledEvent",
    "MarketUpdatedEvent",
    "MarketResolvedEvent",
]
