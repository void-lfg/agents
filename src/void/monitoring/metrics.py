"""
Prometheus metrics for VOID trading agent.

Tracks orders, signals, P&L, and system health.
"""

from prometheus_client import Counter, Gauge, Histogram, Info
import structlog

logger = structlog.get_logger()


# ============== INFO ==============

void_info = Info(
    'void_build_info',
    'VOID trading agent build information',
)

void_info.info({
    'version': '1.0.0',
    'strategy': 'oracle_latency',
    'ai_model': 'glm-4.7',
})


# ============== COUNTERS ==============

# Signals
signals_detected_total = Counter(
    'void_signals_detected_total',
    'Total signals detected',
    ['strategy_type', 'market_id'],
)

signals_verified_total = Counter(
    'void_signals_verified_total',
    'Total signals verified',
    ['strategy_type', 'result'],
)

signals_executed_total = Counter(
    'void_signals_executed_total',
    'Total signals executed',
    ['strategy_type'],
)

signals_rejected_total = Counter(
    'void_signals_rejected_total',
    'Total signals rejected',
    ['reason'],
)

# Orders
orders_submitted_total = Counter(
    'void_orders_submitted_total',
    'Total orders submitted',
    ['side', 'market_id'],
)

orders_filled_total = Counter(
    'void_orders_filled_total',
    'Total orders filled',
    ['side', 'market_id'],
)

orders_cancelled_total = Counter(
    'void_orders_cancelled_total',
    'Total orders cancelled',
    ['reason'],
)

orders_failed_total = Counter(
    'void_orders_failed_total',
    'Total orders failed',
    ['error_type'],
)

# AI Verifications
ai_verifications_total = Counter(
    'void_ai_verifications_total',
    'Total AI verifications',
    ['provider', 'result'],
)

ai_verification_latency_seconds = Histogram(
    'void_ai_verification_latency_seconds',
    'AI verification latency',
    ['provider'],
)


# ============== GAUGES ==============

# Agent Status
agent_status = Gauge(
    'void_agent_status',
    'Current agent status (0=stopped, 1=running, 2=paused, 3=error)',
    ['agent_name'],
)

agent_active_positions = Gauge(
    'void_agent_active_positions',
    'Number of active positions',
    ['agent_name'],
)

agent_last_scan_timestamp = Gauge(
    'void_agent_last_scan_timestamp',
    'Last market scan timestamp',
    ['agent_name'],
)

# P&L
total_pnl_usd = Gauge(
    'void_total_pnl_usd',
    'Total profit/loss in USD',
    ['agent_name', 'strategy'],
)

total_trades = Gauge(
    'void_total_trades',
    'Total number of trades',
    ['agent_name'],
)

win_rate = Gauge(
    'void_win_rate',
    'Win rate (0-1)',
    ['agent_name'],
)

# Market Data
markets_scraped_total = Counter(
    'void_markets_scraped_total',
    'Total markets scraped',
)

opportunity_count = Gauge(
    'void_opportunity_count',
    'Current opportunity count',
    ['strategy_type'],
)

# System
database_connections = Gauge(
    'void_database_connections',
    'Active database connections',
)

redis_connections = Gauge(
    'void_redis_connections',
    'Active Redis connections',
)

websocket_connections = Gauge(
    'void_websocket_connections',
    'Active WebSocket connections',
)


# ============== HISTOGRAMS ==============

order_latency_seconds = Histogram(
    'void_order_latency_seconds',
    'Order placement latency',
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

signal_processing_seconds = Histogram(
    'void_signal_processing_seconds',
    'Signal processing time',
    buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

scan_duration_seconds = Histogram(
    'void_scan_duration_seconds',
    'Market scan duration',
    buckets=[1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
)


# ============== HELPERS ==============

def track_signal_detected(strategy_type: str, market_id: str):
    """Track signal detection."""
    signals_detected_total.labels(
        strategy_type=strategy_type,
        market_id=market_id,
    ).inc()
    logger.debug(
        "metric_signal_detected",
        strategy=strategy_type,
        market=market_id,
    )


def track_signal_verified(strategy_type: str, success: bool):
    """Track signal verification."""
    result = "success" if success else "failed"
    signals_verified_total.labels(
        strategy_type=strategy_type,
        result=result,
    ).inc()


def track_order_submitted(side: str, market_id: str, latency: float):
    """Track order submission."""
    orders_submitted_total.labels(side=side, market_id=market_id).inc()
    order_latency_seconds.observe(latency)


def track_pnl_update(agent_name: str, strategy: str, pnl: float):
    """Track P&L update."""
    total_pnl_usd.labels(agent_name=agent_name, strategy=strategy).set(pnl)


def track_agent_status(agent_name: str, status: str):
    """Track agent status."""
    status_map = {
        "stopped": 0,
        "running": 1,
        "paused": 2,
        "error": 3,
    }
    agent_status.labels(agent_name=agent_name).set(status_map[status])


__all__ = [
    "void_info",
    "signals_detected_total",
    "signals_verified_total",
    "signals_executed_total",
    "orders_submitted_total",
    "orders_filled_total",
    "agent_status",
    "total_pnl_usd",
    "order_latency_seconds",
    "track_signal_detected",
    "track_signal_verified",
    "track_order_submitted",
    "track_pnl_update",
    "track_agent_status",
]
