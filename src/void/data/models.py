"""
SQLAlchemy 2.0 async models for all persistent data.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List
from uuid import UUID, uuid4

from sqlalchemy import (
    String, Text, Numeric, Boolean, DateTime, ForeignKey,
    Index, UniqueConstraint, CheckConstraint, JSON
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB, ARRAY


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


# ============== ENUMS ==============

class AccountStatus(str, Enum):
    """Account status enum."""
    ACTIVE = "active"
    DISABLED = "disabled"
    LOCKED = "locked"


class AgentStatus(str, Enum):
    """Agent status enum."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


class StrategyType(str, Enum):
    """Strategy type enum."""
    ORACLE_LATENCY = "oracle_latency"
    BINARY_ARBITRAGE = "binary_arbitrage"
    LIQUIDITY_PROVISION = "liquidity_provision"
    CUSTOM = "custom"


class OrderSide(str, Enum):
    """Order side enum."""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    """Order status enum."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class SignalStatus(str, Enum):
    """Signal status enum."""
    DETECTED = "detected"
    VERIFIED = "verified"
    EXECUTED = "executed"
    EXPIRED = "expired"
    REJECTED = "rejected"


class MarketStatus(str, Enum):
    """Market status enum."""
    ACTIVE = "active"
    CLOSED = "closed"
    RESOLUTION_PENDING = "resolution_pending"
    RESOLVED = "resolved"


# ============== MODELS ==============

class Account(Base):
    """Trading account with encrypted credentials."""

    __tablename__ = "accounts"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    status: Mapped[AccountStatus] = mapped_column(default=AccountStatus.ACTIVE)

    # Wallet info
    address: Mapped[str] = mapped_column(String(42), unique=True, nullable=False)
    encrypted_private_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_provider: Mapped[str] = mapped_column(String(50), default="local")  # local, x402, aws_kms, vault

    # API credentials (encrypted)
    api_key: Mapped[Optional[str]] = mapped_column(Text)
    api_secret: Mapped[Optional[str]] = mapped_column(Text)
    api_passphrase: Mapped[Optional[str]] = mapped_column(Text)

    # Balances (cached)
    usdc_balance: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    matic_balance: Mapped[Decimal] = mapped_column(Numeric(20, 18), default=0)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    agents: Mapped[List["Agent"]] = relationship(back_populates="account")
    orders: Mapped[List["Order"]] = relationship(back_populates="account")
    positions: Mapped[List["Position"]] = relationship(back_populates="account")

    __table_args__ = (
        Index("ix_accounts_address", "address"),
        Index("ix_accounts_status", "status"),
    )


class Agent(Base):
    """Trading agent instance."""

    __tablename__ = "agents"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    status: Mapped[AgentStatus] = mapped_column(default=AgentStatus.IDLE)

    # Account association
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), nullable=False)

    # Strategy configuration
    strategy_type: Mapped[StrategyType] = mapped_column(nullable=False)
    strategy_config: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Risk parameters
    max_position_size: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=500)
    max_daily_loss: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=100)
    max_concurrent_positions: Mapped[int] = mapped_column(default=3)

    # Performance tracking
    total_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    total_trades: Mapped[int] = mapped_column(default=0)
    win_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0)

    # Lifecycle
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    account: Mapped["Account"] = relationship(back_populates="agents")
    tasks: Mapped[List["Task"]] = relationship(back_populates="agent")
    signals: Mapped[List["Signal"]] = relationship(back_populates="agent")

    __table_args__ = (
        Index("ix_agents_status", "status"),
        Index("ix_agents_strategy", "strategy_type"),
    )


class Task(Base):
    """Scheduled or one-time task for an agent."""

    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)  # scan, execute, monitor, etc.

    # Schedule (cron or interval)
    schedule_type: Mapped[str] = mapped_column(String(20), default="interval")  # interval, cron, once
    schedule_value: Mapped[str] = mapped_column(String(100))  # "30s", "*/5 * * * *", etc.

    # Execution
    is_active: Mapped[bool] = mapped_column(default=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    run_count: Mapped[int] = mapped_column(default=0)
    error_count: Mapped[int] = mapped_column(default=0)

    # Config
    config: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    agent: Mapped["Agent"] = relationship(back_populates="tasks")


class Market(Base):
    """Cached market data from Polymarket."""

    __tablename__ = "markets"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)  # Polymarket market ID
    condition_id: Mapped[str] = mapped_column(String(66), unique=True, nullable=False)
    question_id: Mapped[Optional[str]] = mapped_column(String(66))  # UMA question ID

    # Market info
    question: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(String(200))
    category: Mapped[Optional[str]] = mapped_column(String(100))
    tags: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)

    # Token IDs
    yes_token_id: Mapped[str] = mapped_column(String(100), nullable=False)
    no_token_id: Mapped[str] = mapped_column(String(100), nullable=False)

    # Prices (cached)
    yes_price: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.5"))
    no_price: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.5"))
    spread: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))

    # Volume/Liquidity
    volume_24h: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal("0"))
    liquidity: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal("0"))

    # Status
    status: Mapped[MarketStatus] = mapped_column(default=MarketStatus.ACTIVE)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    resolution_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    outcome: Mapped[Optional[str]] = mapped_column(String(10))  # YES, NO, null

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # AI/Knowledge features
    knowledge_data: Mapped[dict] = mapped_column(JSONB, default=dict)  # Stored knowledge about this market
    last_researched_at: Mapped[Optional[datetime]] = mapped_column(DateTime)  # Last time AI researched this market
    sentiment_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))  # Overall sentiment (-1.0 to +1.0)
    twitter_volume: Mapped[int] = mapped_column(default=0)  # Number of tweets collected
    news_count: Mapped[int] = mapped_column(default=0)  # Number of news articles collected

    # Relationships
    signals: Mapped[List["Signal"]] = relationship(back_populates="market")
    orders: Mapped[List["Order"]] = relationship(back_populates="market")
    positions: Mapped[List["Position"]] = relationship(back_populates="market")

    __table_args__ = (
        Index("ix_markets_status", "status"),
        Index("ix_markets_end_date", "end_date"),
        Index("ix_markets_category", "category"),
        Index("idx_markets_sentiment", "sentiment_score"),
        Index("idx_markets_researched", "last_researched_at"),
    )


class Signal(Base):
    """Trading signal detected by strategy."""

    __tablename__ = "signals"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), nullable=False)
    market_id: Mapped[str] = mapped_column(ForeignKey("markets.id"), nullable=False)

    # Signal details
    strategy_type: Mapped[StrategyType] = mapped_column(nullable=False)
    signal_type: Mapped[str] = mapped_column(String(50), nullable=False)  # oracle_latency, binary_arb, etc.
    predicted_outcome: Mapped[str] = mapped_column(String(10), nullable=False)  # YES, NO, BOTH

    # Pricing
    entry_price: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    expected_payout: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("1.0"))
    profit_margin: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)

    # Verification
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0"))
    verification_source: Mapped[Optional[str]] = mapped_column(String(100))
    verification_data: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Status
    status: Mapped[SignalStatus] = mapped_column(default=SignalStatus.DETECTED)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Metadata
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    agent: Mapped["Agent"] = relationship(back_populates="signals")
    market: Mapped["Market"] = relationship(back_populates="signals")
    orders: Mapped[List["Order"]] = relationship(back_populates="signal")

    __table_args__ = (
        Index("ix_signals_status", "status"),
        Index("ix_signals_strategy", "strategy_type"),
        Index("ix_signals_detected_at", "detected_at"),
    )


class Order(Base):
    """Order submitted to Polymarket CLOB."""

    __tablename__ = "orders"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    market_id: Mapped[str] = mapped_column(ForeignKey("markets.id"), nullable=False)
    signal_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("signals.id"))

    # Order identifiers
    clob_order_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True)
    tx_hash: Mapped[Optional[str]] = mapped_column(String(66))

    # Order details
    token_id: Mapped[str] = mapped_column(String(100), nullable=False)
    side: Mapped[OrderSide] = mapped_column(nullable=False)
    order_type: Mapped[str] = mapped_column(String(20), default="GTC")  # GTC, GTD, FOK, FAK

    # Pricing
    price: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    size: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    filled_size: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    avg_fill_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))

    # Status
    status: Mapped[OrderStatus] = mapped_column(default=OrderStatus.PENDING)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Timing
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Latency tracking
    latency_ms: Mapped[Optional[int]] = mapped_column()  # Time from creation to submission

    # Relationships
    account: Mapped["Account"] = relationship(back_populates="orders")
    market: Mapped["Market"] = relationship(back_populates="orders")
    signal: Mapped[Optional["Signal"]] = relationship(back_populates="orders")

    __table_args__ = (
        Index("ix_orders_status", "status"),
        Index("ix_orders_created_at", "created_at"),
        Index("ix_orders_clob_id", "clob_order_id"),
    )


class Position(Base):
    """Current position in a market."""

    __tablename__ = "positions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    market_id: Mapped[str] = mapped_column(ForeignKey("markets.id"), nullable=False)

    # Position details
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # YES, NO
    token_id: Mapped[str] = mapped_column(String(100), nullable=False)

    # Size and cost
    size: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    avg_entry_price: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    cost_basis: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))

    # Current value
    current_price: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    current_value: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    unrealized_pnl_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"))

    # Realized (after settlement)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    is_closed: Mapped[bool] = mapped_column(default=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Metadata
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    account: Mapped["Account"] = relationship(back_populates="positions")
    market: Mapped["Market"] = relationship(back_populates="positions")

    __table_args__ = (
        UniqueConstraint("account_id", "market_id", "side", name="uq_position"),
        Index("ix_positions_is_closed", "is_closed"),
    )


class TradeLog(Base):
    """Immutable trade history log."""

    __tablename__ = "trade_logs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id"), nullable=False)

    # Trade details
    market_id: Mapped[str] = mapped_column(String(100), nullable=False)
    token_id: Mapped[str] = mapped_column(String(100), nullable=False)
    side: Mapped[OrderSide] = mapped_column(nullable=False)

    # Execution
    price: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    size: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))

    # Identifiers
    clob_trade_id: Mapped[Optional[str]] = mapped_column(String(100))
    tx_hash: Mapped[Optional[str]] = mapped_column(String(66))

    # Timestamp
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_trade_logs_executed_at", "executed_at"),
        Index("ix_trade_logs_account", "account_id"),
    )


# ============== AI FEATURE MODELS ==============

class ConversationHistory(Base):
    """Chat conversation history for each user."""

    __tablename__ = "conversation_history"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # Telegram user ID
    messages: Mapped[List[dict]] = mapped_column(JSON, default=list)  # List of {role, content, timestamp}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_conv_history_user", "user_id"),
        Index("idx_conv_history_updated", "updated_at"),
    )


class TwitterData(Base):
    """Twitter/X data collected for markets."""

    __tablename__ = "twitter_data"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tweet_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(100))
    author_id: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)  # Twitter timestamp
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)  # When we collected it

    # Market association
    market_id: Mapped[Optional[str]] = mapped_column(String(100))  # Polymarket market ID if relevant

    # Sentiment
    sentiment_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))  # -1.0 to +1.0

    # Twitter metadata
    public_metrics: Mapped[Optional[dict]] = mapped_column(JSONB)  # likes, retweets, replies
    metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        Index("idx_twitter_market", "market_id"),
        Index("idx_twitter_collected", "collected_at"),
        Index("idx_twitter_sentiment", "sentiment_score"),
    )


class MarketKnowledge(Base):
    """Knowledge base entries for markets."""

    __tablename__ = "market_knowledge"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    market_id: Mapped[str] = mapped_column(String(100), nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)  # twitter, news, analysis

    # Source info
    source_url: Mapped[Optional[str]] = mapped_column(String(500))
    title: Mapped[Optional[str]] = mapped_column(String(500))

    # Content
    summary: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[Optional[str]] = mapped_column(Text)  # Full content (might be archived to R2)

    # Relevance
    relevance_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))  # 0.0 to 1.0

    # Timestamps
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime)  # If moved to R2

    # R2 storage
    r2_url: Mapped[Optional[str]] = mapped_column(String(1000))  # URL to archived content in R2

    # Additional metadata
    metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        Index("idx_knowledge_market", "market_id"),
        Index("idx_knowledge_type", "content_type"),
        Index("idx_knowledge_relevance", "relevance_score"),
        Index("idx_knowledge_collected", "collected_at"),
    )


class SentimentScore(Base):
    """Sentiment analysis scores for entities."""

    __tablename__ = "sentiment_scores"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)  # market ID, tweet ID, etc.
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # market, tweet, news

    # Sentiment data
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)  # -1.0 to +1.0
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))  # 0.0 to 1.0

    # Analysis metadata
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        Index("idx_sentiment_entity", "entity_id", "entity_type"),
        Index("idx_sentiment_analyzed", "analyzed_at"),
    )


__all__ = [
    "Base",
    "Account",
    "Agent",
    "Task",
    "Market",
    "Signal",
    "Order",
    "Position",
    "TradeLog",
    "ConversationHistory",
    "TwitterData",
    "MarketKnowledge",
    "SentimentScore",
    "AccountStatus",
    "AgentStatus",
    "StrategyType",
    "OrderSide",
    "OrderStatus",
    "SignalStatus",
    "MarketStatus",
]
