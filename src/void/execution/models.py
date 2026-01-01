"""
Execution models for order requests and results.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID


class OrderSide(str, Enum):
    """Order side."""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type."""
    GTC = "GTC"  # Good-Til-Cancelled
    GTD = "GTD"  # Good-Til-Date
    FOK = "FOK"  # Fill-Or-Kill
    FAK = "FAK"  # Fill-And-Kill


class OrderStatus(str, Enum):
    """Order status."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class OrderRequest:
    """Request to create an order."""

    market_id: str
    token_id: str
    side: OrderSide
    order_type: OrderType
    price: Decimal
    size: Decimal
    signal_id: Optional[UUID] = None


@dataclass
class OrderResult:
    """Result from order submission."""

    success: bool
    order_id: Optional[UUID] = None
    clob_order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    error: Optional[str] = None
    filled_price: Optional[Decimal] = None
    filled_size: Optional[Decimal] = None
    latency_ms: Optional[int] = None
    attempts: int = 1


__all__ = [
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "OrderRequest",
    "OrderResult",
]
