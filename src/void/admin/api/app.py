"""
FastAPI admin API for VOID trading agent.

Provides REST API for monitoring and controlling the agent.
"""

from contextlib import asynccontextmanager
from typing import List, Optional
from uuid import UUID

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from void.config import config
from void.data.database import get_db, init_db, close_db
from void.data.models import Agent, AgentStatus, Account, Signal, Order, Position
from void.accounts.service import AccountService
from void.agent.orchestrator import AgentOrchestrator
from void.messaging import EventBus
import structlog

logger = structlog.get_logger()


# ============== LIFESPAN ==============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    # Startup
    logger.info("admin_api_starting")
    await init_db()

    # Initialize event bus
    event_bus = EventBus()
    await event_bus.connect()
    app.state.event_bus = event_bus

    yield

    # Shutdown
    logger.info("admin_api_shutting_down")
    await event_bus.disconnect()
    await close_db()


# ============== APP ==============

app = FastAPI(
    title="VOID Trading Agent API",
    description="Admin interface for autonomous prediction market trading agent",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============== SCHEMAS ==============

class AccountResponse(BaseModel):
    """Account response."""
    id: UUID
    name: str
    address: str
    status: str
    usdc_balance: float
    matic_balance: float
    created_at: str


class AgentResponse(BaseModel):
    """Agent response."""
    id: UUID
    name: str
    status: str
    strategy_type: str
    total_pnl: float
    total_trades: int
    win_rate: float
    started_at: Optional[str]
    last_heartbeat: Optional[str]


class SignalResponse(BaseModel):
    """Signal response."""
    id: UUID
    market_id: str
    strategy_type: str
    predicted_outcome: str
    entry_price: float
    profit_margin: float
    confidence: float
    status: str
    detected_at: str


class PositionResponse(BaseModel):
    """Position response."""
    id: UUID
    market_id: str
    side: str
    size: float
    avg_entry_price: float
    current_value: float
    unrealized_pnl: float
    is_closed: bool


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    environment: str
    database: str


# ============== ENDPOINTS ==============

@app.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check endpoint."""
    try:
        # Test database connection
        await db.execute(select(Account).limit(1))

        return HealthResponse(
            status="healthy",
            version="1.0.0",
            environment=config.environment,
            database="connected",
        )
    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Service unhealthy")


@app.get("/accounts", response_model=List[AccountResponse])
async def list_accounts(
    status: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List all accounts."""
    try:
        query = select(Account)

        if status:
            query = query.where(Account.status == status)

        query = query.offset(offset).limit(limit)

        result = await db.execute(query)
        accounts = result.scalars().all()

        return [
            AccountResponse(
                id=acc.id,
                name=acc.name,
                address=acc.address,
                status=acc.status.value,
                usdc_balance=float(acc.usdc_balance),
                matic_balance=float(acc.matic_balance),
                created_at=acc.created_at.isoformat(),
            )
            for acc in accounts
        ]

    except Exception as e:
        logger.error("list_accounts_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agents", response_model=List[AgentResponse])
async def list_agents(
    status: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List all agents."""
    try:
        query = select(Agent)

        if status:
            query = query.where(Agent.status == status)

        query = query.offset(offset).limit(limit)

        result = await db.execute(query)
        agents = result.scalars().all()

        return [
            AgentResponse(
                id=agent.id,
                name=agent.name,
                status=agent.status.value,
                strategy_type=agent.strategy_type.value,
                total_pnl=float(agent.total_pnl),
                total_trades=agent.total_trades,
                win_rate=float(agent.win_rate),
                started_at=agent.started_at.isoformat() if agent.started_at else None,
                last_heartbeat=agent.last_heartbeat.isoformat() if agent.last_heartbeat else None,
            )
            for agent in agents
        ]

    except Exception as e:
        logger.error("list_agents_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agents/{agent_id}/start")
async def start_agent(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Start an agent."""
    try:
        account_service = AccountService(db)
        orchestrator = AgentOrchestrator(db, account_service, app.state.event_bus)

        await orchestrator.start_agent(agent_id)

        return {"status": "starting", "agent_id": str(agent_id)}

    except Exception as e:
        logger.error("start_agent_failed", agent_id=str(agent_id), error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agents/{agent_id}/stop")
async def stop_agent(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Stop an agent."""
    try:
        account_service = AccountService(db)
        orchestrator = AgentOrchestrator(db, account_service, app.state.event_bus)

        await orchestrator.stop_agent(agent_id)

        return {"status": "stopped", "agent_id": str(agent_id)}

    except Exception as e:
        logger.error("stop_agent_failed", agent_id=str(agent_id), error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/signals", response_model=List[SignalResponse])
async def list_signals(
    agent_id: Optional[UUID] = None,
    status: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List trading signals."""
    try:
        query = select(Signal)

        if agent_id:
            query = query.where(Signal.agent_id == agent_id)

        if status:
            query = query.where(Signal.status == status)

        query = query.order_by(Signal.detected_at.desc()).offset(offset).limit(limit)

        result = await db.execute(query)
        signals = result.scalars().all()

        return [
            SignalResponse(
                id=sig.id,
                market_id=sig.market_id,
                strategy_type=sig.strategy_type.value,
                predicted_outcome=sig.predicted_outcome,
                entry_price=float(sig.entry_price),
                profit_margin=float(sig.profit_margin),
                confidence=float(sig.confidence),
                status=sig.status.value,
                detected_at=sig.detected_at.isoformat(),
            )
            for sig in signals
        ]

    except Exception as e:
        logger.error("list_signals_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/positions", response_model=List[PositionResponse])
async def list_positions(
    account_id: Optional[UUID] = None,
    is_closed: Optional[bool] = None,
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List positions."""
    try:
        query = select(Position)

        if account_id:
            query = query.where(Position.account_id == account_id)

        if is_closed is not None:
            query = query.where(Position.is_closed == is_closed)

        query = query.offset(offset).limit(limit)

        result = await db.execute(query)
        positions = result.scalars().all()

        return [
            PositionResponse(
                id=pos.id,
                market_id=pos.market_id,
                side=pos.side,
                size=float(pos.size),
                avg_entry_price=float(pos.avg_entry_price),
                current_value=float(pos.current_value),
                unrealized_pnl=float(pos.unrealized_pnl),
                is_closed=pos.is_closed,
            )
            for pos in positions
        ]

    except Exception as e:
        logger.error("list_positions_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    # Return metrics in Prometheus format
    from fastapi.responses import Response

    metrics = generate_latest()
    return Response(content=metrics, media_type="text/plain")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=config.admin.api_host,
        port=config.admin.api_port,
    )
