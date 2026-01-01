"""
VOID Admin CLI - Main entry point.

A comprehensive CLI for managing the VOID trading agent.
"""

import click
from pathlib import Path
import sys
import asyncio

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from void.config import config
from void.data.database import init_db, async_session_maker
from void.accounts.service import AccountService
from void.agent.orchestrator import AgentOrchestrator
from void.data.models import Agent, Account, Market, Signal, Position, AgentStatus
from sqlalchemy import select
import structlog
from tabulate import tabulate
from datetime import datetime, timezone


# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()


@click.group()
@click.version_option(version="1.0.0")
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.option('--config-file', type=click.Path(exists=True), help='Custom config file')
@click.pass_context
def cli(ctx, verbose, config_file):
    """
    VOID Admin CLI - Manage your autonomous trading agent.

    \b
    Examples:
        void-admin status              Show system status
        void-admin account list        List all accounts
        void-admin agent start         Start trading agent
        void-admin positions           Show open positions
    """
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose

    # Initialize database if needed
    try:
        asyncio.run(init_db())
    except Exception as e:
        click.echo(f"⚠️  Database initialization warning: {e}", err=True)


@cli.command()
@click.pass_context
def status(ctx):
    """Show system status and statistics."""
    click.echo("\n🔍 VOID Trading Agent Status")
    click.echo("=" * 50)

    async def get_status():
        async with async_session_maker() as db:
            # Get counts
            from sqlalchemy import func

            accounts_count = await db.execute(select(func.count(Account.id)))
            agents_count = await db.execute(select(func.count(Agent.id)))
            signals_count = await db.execute(select(func.count(Signal.id)))
            positions_count = await db.execute(select(func.count(Position.id)))

            # Get active agent
            active_agent = await db.execute(
                select(Agent).where(Agent.status == AgentStatus.RUNNING)
            )
            active_agent = active_agent.scalar_one_or_none()

            return {
                'accounts': accounts_count.scalar() or 0,
                'agents': agents_count.scalar() or 0,
                'signals': signals_count.scalar() or 0,
                'positions': positions_count.scalar() or 0,
                'active_agent': active_agent,
            }

    status_data = asyncio.run(get_status())

    # Display status
    click.echo(f"\n📊 Database:")
    click.echo(f"  Accounts: {status_data['accounts']}")
    click.echo(f"  Agents: {status_data['agents']}")
    click.echo(f"  Signals Detected: {status_data['signals']}")
    click.echo(f"  Open Positions: {status_data['positions']}")

    if status_data['active_agent']:
        agent = status_data['active_agent']
        click.echo(f"\n🤖 Active Agent:")
        click.echo(f"  Name: {agent.name}")
        click.echo(f"  Strategy: {agent.strategy_type.value}")
        click.echo(f"  Status: {agent.status.value}")
        click.echo(f"  Last Heartbeat: {agent.last_heartbeat}")
    else:
        click.echo(f"\n⚠️  No active agents running")

    click.echo(f"\n🔧 Environment: {config.environment}")
    click.echo(f"📝 Debug Mode: {config.debug}")
    click.echo("")


@cli.group()
def account():
    """Manage trading accounts."""
    pass


@account.command('list')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def list_accounts(ctx, format):
    """List all trading accounts."""
    async def get_accounts():
        async with async_session_maker() as db:
            result = await db.execute(
                select(Account).order_by(Account.created_at.desc())
            )
            return result.scalars().all()

    accounts = asyncio.run(get_accounts())

    if not accounts:
        click.echo("No accounts found. Create one with: void-admin account create")
        return

    if format == 'json':
        import json
        data = [
            {
                'id': str(acc.id),
                'name': acc.name,
                'address': acc.address,
                'usdc_balance': float(acc.usdc_balance),
                'matic_balance': float(acc.matic_balance),
                'created_at': acc.created_at.isoformat(),
            }
            for acc in accounts
        ]
        click.echo(json.dumps(data, indent=2))
    else:
        # Table format
        table_data = []
        for acc in accounts:
            table_data.append([
                str(acc.id)[:8] + '...',
                acc.name,
                acc.address[:10] + '...' if acc.address else 'N/A',
                f"${float(acc.usdc_balance):.2f}",
                f"{float(acc.matic_balance):.4f}",
                acc.created_at.strftime('%Y-%m-%d %H:%M'),
            ])

        click.echo(
            tabulate(
                table_data,
                headers=['ID', 'Name', 'Address', 'USDC', 'MATIC', 'Created'],
                tablefmt='grid'
            )
        )


@account.command('create')
@click.option('--name', prompt='Account name', help='Name for this account')
@click.option('--private-key', help='Private key (leave empty to generate new wallet)')
def create_account(name, private_key):
    """Create a new trading account."""
    async def create():
        async with async_session_maker() as db:
            service = AccountService(db)
            account = await service.create_account(
                name=name,
                private_key=private_key,
            )
            await db.commit()
            await db.refresh(account)
            return account

    try:
        click.echo(f"\n🔐 Creating account: {name}")
        account = asyncio.run(create())

        click.echo(f"\n✅ Account created successfully!")
        click.echo(f"  ID: {account.id}")
        click.echo(f"  Name: {account.name}")
        click.echo(f"  Address: {account.address}")

        if not private_key:
            click.echo(f"\n⚠️  IMPORTANT: A new wallet was generated.")
            click.echo(f"  The private key has been encrypted and stored in the database.")
            click.echo(f"  Make sure to backup your database!")

    except Exception as e:
        click.echo(f"❌ Error creating account: {e}", err=True)
        raise click.Abort()


@account.command('sync')
@click.argument('account_id', required=False)
@click.option('--all', 'sync_all', is_flag=True, help='Sync all accounts')
def sync_balance(account_id, sync_all):
    """Sync balances for account(s) from blockchain."""
    async def sync(acc_id, sync_all_flag):
        async with async_session_maker() as db:
            service = AccountService(db)

            if sync_all_flag:
                # Get all accounts
                result = await db.execute(select(Account))
                accounts = result.scalars().all()
            else:
                # Get specific account
                result = await db.execute(select(Account).where(Account.id == acc_id))
                accounts = result.scalars().all()

            if not accounts:
                click.echo("❌ No accounts found", err=True)
                return []

            synced = []
            for account in accounts:
                click.echo(f"\n🔄 Syncing {account.name}...")
                try:
                    synced_account = await service.sync_balances(account.id)
                    await db.commit()
                    synced.append(synced_account)
                    click.echo(f"  ✅ USDC: ${float(synced_account.usdc_balance):.2f}")
                    click.echo(f"  ✅ MATIC: {float(synced_account.matic_balance):.4f}")
                except Exception as e:
                    click.echo(f"  ❌ Error: {e}", err=True)

            return synced

    if not sync_all and not account_id:
        click.echo("❌ Please provide ACCOUNT_ID or use --all flag", err=True)
        raise click.Abort()

    asyncio.run(sync(account_id, sync_all))


@cli.group()
def agent():
    """Manage trading agents."""
    pass


@agent.command('list')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
def list_agents(format):
    """List all agents."""
    async def get_agents():
        async with async_session_maker() as db:
            result = await db.execute(
                select(Agent).order_by(Agent.created_at.desc())
            )
            return result.scalars().all()

    agents = asyncio.run(get_agents())

    if not agents:
        click.echo("No agents found. Create one with: void-admin agent create")
        return

    if format == 'json':
        import json
        data = [
            {
                'id': str(agent.id),
                'name': agent.name,
                'strategy': agent.strategy_type.value,
                'status': agent.status.value,
                'account_id': str(agent.account_id),
                'created_at': agent.created_at.isoformat(),
            }
            for agent in agents
        ]
        click.echo(json.dumps(data, indent=2))
    else:
        table_data = []
        for agent in agents:
            # Add emoji for status
            status_emoji = {
                'IDLE': '💤',
                'RUNNING': '🏃',
                'STOPPED': '⏹️',
                'ERROR': '❌',
            }.get(agent.status.value, '❓')

            table_data.append([
                status_emoji,
                agent.name,
                agent.strategy_type.value,
                agent.status.value,
                str(agent.account_id)[:8] + '...',
                agent.max_position_size,
                agent.created_at.strftime('%Y-%m-%d'),
            ])

        click.echo(
            tabulate(
                table_data,
                headers=['', 'Name', 'Strategy', 'Status', 'Account', 'Max Pos', 'Created'],
                tablefmt='grid'
            )
        )


@agent.command('start')
@click.argument('agent_id')
def start_agent(agent_id):
    """Start a trading agent."""
    async def start():
        async with async_session_maker() as db:
            service = AccountService(db)
            orchestrator = AgentOrchestrator(db, service, None)  # No event bus for CLI
            await orchestrator.start_agent(agent_id)
            return agent_id

    try:
        click.echo(f"\n🚀 Starting agent: {agent_id}")
        asyncio.run(start())
        click.echo("✅ Agent started successfully!")
        click.echo(f"   Monitor with: void-admin agent status {agent_id}")
    except Exception as e:
        click.echo(f"❌ Error starting agent: {e}", err=True)
        raise click.Abort()


@agent.command('stop')
@click.argument('agent_id')
def stop_agent(agent_id):
    """Stop a trading agent."""
    async def stop():
        async with async_session_maker() as db:
            service = AccountService(db)
            orchestrator = AgentOrchestrator(db, service, None)
            await orchestrator.stop_agent(agent_id)
            return agent_id

    try:
        click.echo(f"\n⏹️  Stopping agent: {agent_id}")
        asyncio.run(stop())
        click.echo("✅ Agent stopped successfully!")
    except Exception as e:
        click.echo(f"❌ Error stopping agent: {e}", err=True)
        raise click.Abort()


@cli.group()
def market():
    """View and analyze markets."""
    pass


@market.command('list')
@click.option('--limit', default=20, help='Number of markets to show')
@click.option('--category', help='Filter by category')
@click.option('--active-only', is_flag=True, help='Show only active markets')
def list_markets(limit, category, active_only):
    """List Polymarket markets."""
    async def get_markets():
        async with async_session_maker() as db:
            query = select(Market).order_by(Market.volume_24h.desc())

            if category:
                query = query.where(Market.category == category)

            if active_only:
                from void.data.models import MarketStatus
                query = query.where(Market.status == MarketStatus.ACTIVE)

            query = query.limit(limit)

            result = await db.execute(query)
            return result.scalars().all()

    markets = asyncio.run(get_markets())

    if not markets:
        click.echo("No markets found in database.")
        click.echo("Hint: Markets sync automatically when agent runs.")
        return

    table_data = []
    for market in markets:
        table_data.append([
            market.question[:50] + '...' if len(market.question) > 50 else market.question,
            market.category,
            f"${float(market.volume_24h):.0f}",
            f"{float(market.yes_price):.3f}" if market.yes_price else 'N/A',
            f"{float(market.no_price):.3f}" if market.no_price else 'N/A',
            market.status.value,
        ])

    click.echo(
        tabulate(
            table_data,
            headers=['Question', 'Category', 'Volume', 'YES', 'NO', 'Status'],
            tablefmt='grid'
        )
    )


@cli.group()
def position():
    """View and manage trading positions."""
    pass


@position.command('list')
@click.option('--open-only', is_flag=True, help='Show only open positions')
@click.option('--account-id', help='Filter by account')
def list_positions(open_only, account_id):
    """List trading positions."""
    async def get_positions():
        async with async_session_maker() as db:
            query = select(Position).order_by(Position.entered_at.desc())

            if open_only:
                from void.data.models import PositionStatus
                query = query.where(Position.status == PositionStatus.OPEN)

            if account_id:
                query = query.where(Position.account_id == account_id)

            result = await db.execute(query)
            return result.scalars().all()

    positions = asyncio.run(get_positions())

    if not positions:
        click.echo("No positions found.")
        return

    table_data = []
    for pos in positions:
        pnl = float(pos.pnl) if pos.pnl else 0.0
        pnl_color = "+" if pnl > 0 else ""

        table_data.append([
            str(pos.id)[:8] + '...',
            pos.market_id[:10] + '...',
            pos.side,
            f"${float(pos.size_usd):.2f}",
            f"{float(pos.entry_price):.4f}",
            pos.status.value,
            f"{pnl_color}${pnl:.2f}" if pnl != 0 else '$0.00',
            pos.entered_at.strftime('%Y-%m-%d %H:%M'),
        ])

    click.echo(
        tabulate(
            table_data,
            headers=['ID', 'Market', 'Side', 'Size', 'Entry', 'Status', 'P&L', 'Entered'],
            tablefmt='grid'
        )
    )


@cli.group()
def signal():
    """View trading signals."""
    pass


@signal.command('list')
@click.option('--limit', default=20, help='Number of signals to show')
@click.option('--strategy', help='Filter by strategy type')
def list_signals(limit, strategy):
    """List recent trading signals."""
    async def get_signals():
        async with async_session_maker() as db:
            from void.data.models import SignalStatus

            query = select(Signal).order_by(Signal.detected_at.desc())

            if strategy:
                query = query.where(Signal.strategy_type == strategy)

            query = query.limit(limit)

            result = await db.execute(query)
            return result.scalars().all()

    signals = asyncio.run(get_signals())

    if not signals:
        click.echo("No signals found.")
        return

    table_data = []
    for sig in signals:
        confidence = f"{float(sig.confidence)*100:.1f}%" if sig.confidence else 'N/A'

        table_data.append([
            str(sig.id)[:8] + '...',
            sig.market_id[:10] + '...',
            sig.strategy_type,
            sig.signal_type,
            sig.predicted_outcome,
            confidence,
            f"{float(sig.profit_margin)*100:.1f}%" if sig.profit_margin else 'N/A',
            sig.status.value,
            sig.detected_at.strftime('%Y-%m-%d %H:%M'),
        ])

    click.echo(
        tabulate(
            table_data,
            headers=['ID', 'Market', 'Strategy', 'Type', 'Outcome', 'Confidence', 'Profit', 'Status', 'Detected'],
            tablefmt='grid'
        )
    )


@cli.command()
@click.option('--follow', '-f', is_flag=True, help='Follow log output')
@click.option('--lines', '-n', default=50, help='Number of lines to show')
def logs(follow, lines):
    """View agent logs."""
    log_file = Path("logs/agent/void.log")

    if not log_file.exists():
        click.echo("❌ Log file not found. Has the agent been run?")
        raise click.Abort()

    if follow:
        click.echo(f"📋 Following logs (Ctrl+C to stop)...\n")
        import subprocess
        try:
            subprocess.run(['tail', '-f', str(log_file)])
        except KeyboardInterrupt:
            click.echo("\n\n👋 Stopped following logs")
    else:
        import subprocess
        try:
            subprocess.run(['tail', '-n', str(lines), str(log_file)])
        except FileNotFoundError:
            # Fallback if tail not available
            with open(log_file, 'r') as f:
                lines_list = f.readlines()
                for line in lines_list[-lines:]:
                    click.echo(line.rstrip())


@cli.command()
def test_api():
    """Test Polymarket API connection."""
    async def test_connection():
        from void.data.feeds.polymarket.gamma_client import GammaClient
        from void.data.feeds.polymarket.clob_client import ClobClient

        click.echo("\n🔌 Testing Polymarket API Connection")
        click.echo("=" * 50)

        # Test Gamma API
        click.echo("\n1. Testing Gamma API (Market Discovery)...")
        try:
            gamma = GammaClient()
            markets = await gamma.get_markets(limit=1)
            if markets:
                click.echo(f"   ✅ Gamma API working - Found {len(markets)} markets")
            else:
                click.echo(f"   ⚠️  Gamma API connected but no markets returned")
        except Exception as e:
            click.echo(f"   ❌ Gamma API error: {e}")

        # Test CLOB API
        click.echo("\n2. Testing CLOB API (Trading)...")
        try:
            clob = ClobClient()
            # Just test connection, don't place orders
            click.echo(f"   ✅ CLOB API initialized")
            click.echo(f"   📝 CLOB URL: {config.polymarket_clob_url}")
        except Exception as e:
            click.echo(f"   ❌ CLOB API error: {e}")

        click.echo("\n" + "=" * 50)
        click.echo("✅ API test complete\n")

    asyncio.run(test_connection())


if __name__ == '__main__':
    cli(obj={})
