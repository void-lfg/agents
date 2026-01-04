"""
VOID Telegram Bot - Main bot implementation.

Provides Telegram interface for controlling and monitoring VOID trading agent.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)

from void.bot.config import TelegramBotConfig
from void.data.database import async_session_maker
from void.data.models import Agent, Account, Position, Signal, AgentStatus
from void.accounts.service import AccountService
from void.agent.orchestrator import AgentOrchestrator
from void.messaging import EventBus
from void.messaging.events import EventType
from sqlalchemy import select, func
import structlog

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
struct_logger = structlog.get_logger()


class VoidBot:
    """VOID Trading Agent Telegram Bot."""

    def __init__(self, config: TelegramBotConfig):
        """Initialize bot."""
        self.config = config
        self.application: Optional[Application] = None
        self.event_bus: Optional[EventBus] = None

    async def is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized."""
        if not self.config.allowed_user_ids:
            return True  # Allow all if list is empty
        return user_id in self.config.allowed_user_ids

    async def is_admin(self, user_id: int) -> bool:
        """Check if user is admin."""
        if not self.config.admin_user_ids:
            return True  # Allow all if list is empty
        return user_id in self.config.admin_user_ids

    # ============== Command Handlers ==============

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user_id = update.effective_user.id

        if not await self.is_authorized(user_id):
            await update.message.reply_text(
                "⛔ You are not authorized to use this bot."
            )
            return

        welcome_message = (
            "🤖 *Welcome to VOID Trading Agent!*\n\n"
            "I'm your autonomous trading assistant for Polymarket prediction markets.\n\n"
            "*Quick Start:*\n"
            "/menu - Interactive management menu\n"
            "/status - Check system status\n"
            "/help - Show all commands\n\n"
            "*Need Help?*\n"
            "Use /menu for easy navigation or /help to see all commands.\n\n"
            "Let's make some money! 🚀💰"
        )

        await update.message.reply_text(welcome_message, parse_mode="Markdown")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        user_id = update.effective_user.id

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        help_text = """
📖 *VOID Bot Commands*

*🎛️ Navigation:*
/menu - Interactive management menu
/help - Show this message

*📊 Monitoring:*
/status - System status and stats
/portfolio - Account balances and value
/positions - Open trading positions
/signals - Recent trading signals
/agents - List all agents
/history - Trading history
/logs - Recent system logs
/stats - Performance statistics

*🏦 Account Management:*
/create_account - Create new trading account
/remove_account - Remove trading account
/create_agent - Create new trading agent
/sync - Sync wallet balances
/deposit - Deposit information
/withdraw - Withdrawal guide

*🤖 Agent Control:*
/start_agent - Start trading agent
/stop_agent - Stop trading agent
/agent - Quick agent control

*⚙️ Settings:*
/settings - Configure bot settings

*❓ Other:*
/close_position - Close a position
/about - About VOID

💡 Use /menu for easy navigation!
"""

        await update.message.reply_text(help_text)

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        user_id = update.effective_user.id

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        try:
            async with async_session_maker() as db:
                # Get counts
                accounts_count = await db.execute(select(func.count(Account.id)))
                agents_count = await db.execute(select(func.count(Agent.id)))
                signals_count = await db.execute(select(func.count(Signal.id)))
                positions_count = await db.execute(
                    select(func.count(Position.id)).where(Position.is_closed == False)
                )

                # Get active agent
                active_agent = await db.execute(
                    select(Agent).where(Agent.status == AgentStatus.RUNNING)
                )
                active_agent = active_agent.scalar_one_or_none()

                # Calculate total P&L
                total_pnl_result = await db.execute(
                    select(func.sum(Position.unrealized_pnl)).where(Position.unrealized_pnl.isnot(None))
                )
                total_pnl = total_pnl_result.scalar() or 0

            status_text = (
                "🔍 *System Status*\n\n"
                f"📊 *Database:*\n"
                f"  • Accounts: {accounts_count.scalar() or 0}\n"
                f"  • Agents: {agents_count.scalar() or 0}\n"
                f"  • Signals: {signals_count.scalar() or 0}\n"
                f"  • Open Positions: {positions_count.scalar() or 0}\n\n"
            )

            if active_agent:
                status_text += (
                    f"🤖 *Active Agent:*\n"
                    f"  • Name: {active_agent.name}\n"
                    f"  • Strategy: {active_agent.strategy_type.value}\n"
                    f"  • Status: {active_agent.status.value}\n"
                    f"  • Heartbeat: {active_agent.last_heartbeat.strftime('%H:%M:%S') if active_agent.last_heartbeat else 'N/A'}\n\n"
                )
            else:
                status_text += "🤖 *Active Agent:* None running\n\n"

            status_text += f"💰 *Total P&L:* ${float(total_pnl):.2f}\n"

            await update.message.reply_text(status_text, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Status error: {e}", exc_info=True)
            await update.message.reply_text(
                f"⚠️ Could not retrieve status. Database may be unavailable.\n\n"
                f"Error: {str(e)[:100]}\n\n"
                f"💡 Make sure PostgreSQL is running and migrations are applied."
            )

    async def portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /portfolio command."""
        user_id = update.effective_user.id

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        async with async_session_maker() as db:
            result = await db.execute(select(Account))
            accounts = result.scalars().all()

        if not accounts:
            await update.message.reply_text("📊 No accounts found")
            return

        portfolio_text = "💼 *Portfolio Overview*\n\n"

        for account in accounts:
            portfolio_text += (
                f"🏦 *{account.name}*\n"
                f"  • USDC: ${float(account.usdc_balance):.2f}\n"
                f"  • MATIC: {float(account.matic_balance):.4f}\n"
                f"  • Address: `{account.address[:10]}...{account.address[-6:]}`\n\n"
            )

        await update.message.reply_text(portfolio_text, parse_mode="Markdown")

    async def positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command."""
        user_id = update.effective_user.id

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        try:
            async with async_session_maker() as db:
                result = await db.execute(
                    select(Position)
                    .where(Position.is_closed == False)
                    .order_by(Position.opened_at.desc())
                    .limit(10)
                )
                positions = result.scalars().all()

            if not positions:
                await update.message.reply_text("📊 No open positions")
                return

            positions_text = f"📊 *Open Positions* ({len(positions)})\n\n"

            for pos in positions[:5]:  # Show max 5
                pnl = float(pos.unrealized_pnl)
                pnl_symbol = "+" if pnl > 0 else ""
                positions_text += (
                    f"🎯 *Market:* {pos.market_id[:10]}...\n"
                    f"  • Side: {pos.side}\n"
                    f"  • Size: {float(pos.size):.2f}\n"
                    f"  • Entry: {float(pos.avg_entry_price):.4f}\n"
                    f"  • P&L: {pnl_symbol}${pnl:.2f}\n"
                    f"  • Opened: {pos.opened_at.strftime('%m/%d %H:%M')}\n\n"
                )

            await update.message.reply_text(positions_text, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Positions error: {e}", exc_info=True)
            await update.message.reply_text(
                f"⚠️ Could not retrieve positions. Database may be unavailable.\n\n"
                f"Error: {str(e)[:100]}"
            )

    async def signals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /signals command."""
        user_id = update.effective_user.id

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        async with async_session_maker() as db:
            result = await db.execute(
                select(Signal)
                .order_by(Signal.detected_at.desc())
                .limit(10)
            )
            signals = result.scalars().all()

        if not signals:
            await update.message.reply_text("📊 No signals yet")
            return

        signals_text = f"📈 *Recent Signals* ({len(signals)})\n\n"

        for sig in signals[:5]:  # Show max 5
            confidence = f"{float(sig.confidence)*100:.0f}%" if sig.confidence else "N/A"
            profit = f"{float(sig.profit_margin)*100:.1f}%" if sig.profit_margin else "N/A"

            signals_text += (
                f"🎯 *Signal:* {sig.signal_type}\n"
                f"  • Market: {sig.market_id[:10]}...\n"
                f"  • Outcome: {sig.predicted_outcome}\n"
                f"  • Confidence: {confidence}\n"
                f"  • Profit: {profit}\n"
                f"  • Status: {sig.status.value}\n"
                f"  • Time: {sig.detected_at.strftime('%m/%d %H:%M')}\n\n"
            )

        await update.message.reply_text(signals_text, parse_mode="Markdown")

    async def agents(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /agents command."""
        user_id = update.effective_user.id

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        async with async_session_maker() as db:
            result = await db.execute(
                select(Agent).order_by(Agent.created_at.desc())
            )
            agents = result.scalars().all()

        if not agents:
            await update.message.reply_text("🤖 No agents found")
            return

        agents_text = f"🤖 *Trading Agents* ({len(agents)})\n\n"

        for agent in agents:
            status_emoji = {
                "IDLE": "💤",
                "RUNNING": "🏃",
                "STOPPED": "⏹️",
                "ERROR": "❌",
            }.get(agent.status.value, "❓")

            agents_text += (
                f"{status_emoji} *{agent.name}*\n"
                f"  • Strategy: {agent.strategy_type.value}\n"
                f"  • Status: {agent.status.value}\n"
                f"  • Max Position: ${agent.max_position_size}\n"
                f"  • Created: {agent.created_at.strftime('%m/%d %Y')}\n\n"
            )

        await update.message.reply_text(agents_text, parse_mode="Markdown")

    async def agent_control(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /agent command with inline keyboard."""
        user_id = update.effective_user.id

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        if not await self.is_admin(user_id):
            await update.message.reply_text(
                "⛔ You need admin privileges to control agents."
            )
            return

        # Get running agents
        async with async_session_maker() as db:
            result = await db.execute(
                select(Agent).where(Agent.status == AgentStatus.RUNNING)
            )
            running_agents = result.scalars().all()

        if not running_agents:
            await update.message.reply_text(
                "🤖 No running agents to control.\n\n"
                "Use the agent list to see available agents."
            )
            return

        # Create inline keyboard
        keyboard = []
        for agent in running_agents:
            keyboard.append([
                InlineKeyboardButton(f"⏹️ Stop {agent.name}", callback_data=f"stop_{agent.id}")
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🎛️ *Agent Control*\n\n"
            "Select an agent to control:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks."""
        query = update.callback_query
        user_id = query.from_user.id

        if not await self.is_admin(user_id):
            await query.answer("⛔ Not authorized")
            return

        await query.answer()

        action, agent_id = query.data.split("_")

        if action == "stop":
            try:
                async with async_session_maker() as db:
                    account_service = AccountService(db)
                    orchestrator = AgentOrchestrator(db, account_service, None)
                    await orchestrator.stop_agent(agent_id)

                await query.edit_message_text(
                    f"✅ Agent stopped successfully!"
                )
            except Exception as e:
                await query.edit_message_text(
                    f"❌ Error stopping agent: {str(e)}"
                )

    async def create_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /create_account command - Create a new trading account."""
        user_id = update.effective_user.id

        if not await self.is_admin(user_id):
            await update.message.reply_text("⛔ Admin privileges required")
            return

        try:
            from void.accounts.service import AccountService
            from eth_account import Account
            from datetime import datetime

            async with async_session_maker() as db:
                service = AccountService(db)

                # Generate new wallet
                account_name = f"account-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                acct = Account.create()
                private_key = acct.key.hex()

                account = await service.create_account(
                    name=account_name,
                    private_key=private_key,
                )

                await db.commit()
                await db.refresh(account)

                # Show private key to user NOW - this is the only chance
                message = f"""
✅ *Account Created Successfully!*

🏦 *Account Details:*
  • Name: {account.name}
  • Address: `{account.address}`

🔐 *PRIVATE KEY - SAVE THIS NOW:*
`{private_key}`

⚠️ *CRITICAL:*
  • Save this private key securely NOW
  • This is the ONLY time you'll see it
  • System will encrypt and store it, but you need the backup
  • Use this key to import wallet into MetaMask或其他钱包

📝 *Next Steps:*
  1. Save your private key above
  2. Import into MetaMask using the private key
  3. Fund the wallet with USDC on Polygon network
  4. Use /sync to check your balance
"""

                await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Create account error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error creating account: {str(e)[:100]}")

    async def remove_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /remove_account command - Remove an account with confirmation."""
        user_id = update.effective_user.id

        if not await self.is_admin(user_id):
            await update.message.reply_text("⛔ Admin privileges required")
            return

        try:
            async with async_session_maker() as db:
                from sqlalchemy import select

                result = await db.execute(select(Account))
                accounts = result.scalars().all()

                if not accounts:
                    await update.message.reply_text("📭 No accounts found")
                    return

                # Create inline keyboard with account options
                keyboard = []
                for acc in accounts[:10]:  # Max 10 accounts
                    keyboard.append([
                        InlineKeyboardButton(
                            f"🗑️ {acc.name} ({acc.address[:10]}...)",
                            callback_data=f"remove_account_{acc.id}"
                        )
                    ])

                keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="menu_cancel")])

                reply_markup = InlineKeyboardMarkup(keyboard)

                message = f"""
🗑️ *Remove Account*

⚠️ *WARNING: This action is irreversible!*

Select an account to remove:

*Accounts ({len(accounts)}):*
"""

                await update.message.reply_text(
                    message,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )

        except Exception as e:
            logger.error(f"Remove account error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def create_agent(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /create_agent command - Create a new trading agent."""
        user_id = update.effective_user.id

        if not await self.is_admin(user_id):
            await update.message.reply_text("⛔ Admin privileges required")
            return

        try:
            from void.data.models import StrategyType
            from datetime import datetime, timezone

            async with async_session_maker() as db:
                # Get first account
                from sqlalchemy import select
                result = await db.execute(select(Account).limit(1))
                account = result.scalar_one_or_none()

                if not account:
                    await update.message.reply_text(
                        "❌ No accounts found. Create one first with /create_account"
                    )
                    return

                # Create agent
                agent = Agent(
                    name=f"oracle-agent-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                    status=AgentStatus.IDLE,
                    account_id=account.id,
                    strategy_type=StrategyType.ORACLE_LATENCY,
                    strategy_config={
                        "max_position_size_usd": "500",
                        "max_positions": 3,
                        "min_profit_margin": "0.01",
                        "min_discount": "0.01",
                        "max_hours_since_end": 24,
                        "use_ai_verification": True,
                    },
                    max_position_size=500,
                    max_daily_loss=100,
                    max_concurrent_positions=3,
                )

                db.add(agent)
                await db.commit()
                await db.refresh(agent)

                message = (
                    f"✅ *Agent Created Successfully!*\n\n"
                    f"🤖 *Agent Details:*\n"
                    f"  • Name: {agent.name}\n"
                    f"  • Strategy: {agent.strategy_type.value}\n"
                    f"  • Account: {account.name}\n"
                    f"  • Max Position: ${agent.max_position_size}\n"
                    f"  • Max Positions: {agent.max_concurrent_positions}\n\n"
                    f"🚀 Start the agent with:\n"
                    f"  /agent"
                )

                await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Create agent error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error creating agent: {str(e)[:100]}")

    async def sync_balances(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /sync command - Sync wallet balances from blockchain."""
        user_id = update.effective_user.id

        if not await self.is_admin(user_id):
            await update.message.reply_text("⛔ Admin privileges required")
            return

        try:
            from void.accounts.service import AccountService

            async with async_session_maker() as db:
                service = AccountService(db)

                # Get all accounts
                from sqlalchemy import select
                result = await db.execute(select(Account))
                accounts = result.scalars().all()

                if not accounts:
                    await update.message.reply_text("❌ No accounts found")
                    return

                message = "🔄 *Syncing Balances...*\n\n"

                for account in accounts:
                    try:
                        synced = await service.sync_balances(account.id)
                        await db.commit()
                        await db.refresh(synced)

                        message += (
                            f"✅ *{synced.name}*\n"
                            f"  • USDC: ${float(synced.usdc_balance):.2f}\n"
                            f"  • MATIC: {float(synced.matic_balance):.4f}\n\n"
                        )
                    except Exception as e:
                        message += f"❌ *{account.name}*: Failed - {str(e)[:50]}\n\n"

                message += "💰 Balances synced successfully!"
                await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Sync error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error syncing: {str(e)[:100]}")

    async def menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /menu command - Show interactive management menu."""
        user_id = update.effective_user.id

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        keyboard = [
            [
                InlineKeyboardButton("📊 Status", callback_data="menu_status"),
                InlineKeyboardButton("💰 Portfolio", callback_data="menu_portfolio"),
            ],
            [
                InlineKeyboardButton("🤖 Agents", callback_data="menu_agents"),
                InlineKeyboardButton("📈 Positions", callback_data="menu_positions"),
            ],
            [
                InlineKeyboardButton("📜 History", callback_data="menu_history"),
                InlineKeyboardButton("📋 Logs", callback_data="menu_logs"),
            ],
            [
                InlineKeyboardButton("📊 Stats", callback_data="menu_stats"),
                InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings"),
            ],
            [
                InlineKeyboardButton("➕ Create Account", callback_data="menu_create_account"),
                InlineKeyboardButton("➕ Create Agent", callback_data="menu_create_agent"),
            ],
            [
                InlineKeyboardButton("🗑️ Remove Account", callback_data="menu_remove_account"),
            ],
            [
                InlineKeyboardButton("💵 Deposit", callback_data="menu_deposit"),
                InlineKeyboardButton("💸 Withdraw", callback_data="menu_withdraw"),
            ],
            [
                InlineKeyboardButton("🔄 Sync Balances", callback_data="menu_sync"),
            ],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🎛️ *VOID Management Menu*\n\nSelect an action:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

    async def menu_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle menu button callbacks."""
        query = update.callback_query
        user_id = query.from_user.id

        await query.answer()

        action = query.data

        logger.info(f"Menu callback: action={action}, user_id={user_id}")

        # Route to appropriate handler with admin check
        try:
            # Handle remove_account callbacks (pattern: remove_account_<id>)
            if action.startswith("remove_account_"):
                await self._handle_remove_account(query, user_id, action)
            elif action.startswith("confirm_remove_"):
                await self._confirm_remove_account(query, user_id, action)
            elif action == "menu_cancel":
                await query.message.reply_text("❌ Cancelled")
            elif action == "menu_status":
                await self._cb_status(query, user_id)
            elif action == "menu_portfolio" or action == "menu_accounts":
                await self._cb_portfolio(query, user_id)
            elif action == "menu_agents":
                await self._cb_agents(query, user_id)
            elif action == "menu_positions":
                await self._cb_positions(query, user_id)
            elif action == "menu_history":
                await self._cb_history(query, user_id)
            elif action == "menu_logs":
                await self._cb_logs(query, user_id)
            elif action == "menu_stats":
                await self._cb_stats(query, user_id)
            elif action == "menu_settings":
                await self._cb_settings(query, user_id)
            elif action == "menu_create_account":
                await self._cb_create_account(query, user_id)
            elif action == "menu_create_agent":
                await self._cb_create_agent(query, user_id)
            elif action == "menu_remove_account":
                await self._cb_remove_account(query, user_id)
            elif action == "menu_deposit":
                await self._cb_deposit(query, user_id)
            elif action == "menu_withdraw":
                await self._cb_withdraw(query, user_id)
            elif action == "menu_sync":
                await self._cb_sync(query, user_id)
            elif action == "menu_back":
                await self.menu(update, context)
            else:
                await query.message.reply_text("❌ Unknown action")
        except Exception as e:
            logger.error(f"Menu callback error for {action}: {e}", exc_info=True)
            await query.message.reply_text(f"❌ Error: {str(e)[:100]}")

    # ============== Callback Handlers for Menu ==============

    async def _cb_status(self, query, user_id):
        """Callback for status - sends new message."""
        if not await self.is_authorized(user_id):
            await query.message.reply_text("⛔ Not authorized")
            return

        try:
            async with async_session_maker() as db:
                from sqlalchemy import select, func
                from void.data.models import Signal, Position, AgentStatus

                accounts_count = await db.execute(select(func.count(Account.id)))
                agents_count = await db.execute(select(func.count(Agent.id)))
                signals_count = await db.execute(select(func.count(Signal.id)))
                positions_count = await db.execute(
                    select(func.count(Position.id)).where(Position.is_closed == False)
                )

                active_agent = await db.execute(
                    select(Agent).where(Agent.status == AgentStatus.RUNNING)
                )
                active_agent = active_agent.scalar_one_or_none()

                total_pnl_result = await db.execute(
                    select(func.sum(Position.unrealized_pnl)).where(Position.unrealized_pnl.isnot(None))
                )
                total_pnl = total_pnl_result.scalar() or 0

            status_text = (
                "📊 *System Status*\n\n"
                f"  • Accounts: {accounts_count.scalar() or 0}\n"
                f"  • Agents: {agents_count.scalar() or 0}\n"
                f"  • Signals: {signals_count.scalar() or 0}\n"
                f"  • Open Positions: {positions_count.scalar() or 0}\n\n"
            )

            if active_agent:
                status_text += (
                    f"🤖 *Active Agent:*\n"
                    f"  • {active_agent.name}\n"
                    f"  • {active_agent.strategy_type.value}\n"
                )

            status_text += f"\n💰 Total P&L: ${float(total_pnl):.2f}"

            await query.message.reply_text(status_text, parse_mode="Markdown")
        except Exception as e:
            await query.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def _cb_portfolio(self, query, user_id):
        """Callback for portfolio - sends new message."""
        if not await self.is_authorized(user_id):
            await query.message.reply_text("⛔ Not authorized")
            return

        try:
            async with async_session_maker() as db:
                from sqlalchemy import select

                result = await db.execute(select(Account))
                accounts = result.scalars().all()

                if not accounts:
                    await query.message.reply_text("📭 No accounts found")
                    return

                total_usdc = sum(float(a.usdc_balance or 0) for a in accounts)
                total_matic = sum(float(a.matic_balance or 0) for a in accounts)

                portfolio_text = (
                    f"💰 *Portfolio Overview*\n\n"
                    f"📊 *Total Balance:*\n"
                    f"  • USDC: ${total_usdc:.2f}\n"
                    f"  • MATIC: {total_matic:.4f}\n\n"
                    f"*Accounts ({len(accounts)}):*\n"
                )

                for acc in accounts[:5]:
                    portfolio_text += (
                        f"\n  • {acc.name}\n"
                        f"    USDC: ${float(acc.usdc_balance or 0):.2f}\n"
                        f"    MATIC: {float(acc.matic_balance or 0):.4f}\n"
                    )

                await query.message.reply_text(portfolio_text, parse_mode="Markdown")
        except Exception as e:
            await query.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def _cb_agents(self, query, user_id):
        """Callback for agents - sends new message."""
        if not await self.is_authorized(user_id):
            await query.message.reply_text("⛔ Not authorized")
            return

        try:
            async with async_session_maker() as db:
                from sqlalchemy import select

                result = await db.execute(select(Agent))
                agents = result.scalars().all()

                if not agents:
                    await query.message.reply_text("📭 No agents found")
                    return

                agents_text = f"🤖 Trading Agents ({len(agents)})\n\n"

                for agent in agents:
                    status_emoji = {
                        "IDLE": "💤",
                        "RUNNING": "🟢",
                        "STOPPED": "⏹️",
                        "ERROR": "🔴"
                    }.get(agent.status.value, "❓")

                    agents_text += (
                        f"{status_emoji} {agent.name}\n"
                        f"  • ID: {agent.id}\n"
                        f"  • Strategy: {agent.strategy_type.value}\n"
                        f"  • Status: {agent.status.value}\n\n"
                    )

                await query.message.reply_text(agents_text)
        except Exception as e:
            await query.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def _cb_positions(self, query, user_id):
        """Callback for positions - sends new message."""
        if not await self.is_authorized(user_id):
            await query.message.reply_text("⛔ Not authorized")
            return

        try:
            async with async_session_maker() as db:
                from sqlalchemy import select

                result = await db.execute(
                    select(Position)
                    .where(Position.is_closed == False)
                    .order_by(Position.opened_at.desc())
                    .limit(10)
                )
                positions = result.scalars().all()

                if not positions:
                    await query.message.reply_text("📭 No open positions")
                    return

                positions_text = f"📈 *Open Positions ({len(positions)})*\n\n"

                for pos in positions[:5]:
                    pnl = float(pos.unrealized_pnl) if pos.unrealized_pnl else 0
                    emoji = "🟢" if pnl >= 0 else "🔴"

                    positions_text += (
                        f"{emoji} *{pos.market_id[:20]}...*\n"
                        f"  • Side: {pos.side}\n"
                        f"  • Size: ${float(pos.size):.2f}\n"
                        f"  • P&L: ${pnl:.2f}\n\n"
                    )

                await query.message.reply_text(positions_text, parse_mode="Markdown")
        except Exception as e:
            await query.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def _cb_history(self, query, user_id):
        """Callback for history - sends new message."""
        if not await self.is_authorized(user_id):
            await query.message.reply_text("⛔ Not authorized")
            return

        try:
            async with async_session_maker() as db:
                from sqlalchemy import select, desc

                result = await db.execute(
                    select(Position)
                    .where(Position.is_closed == True)
                    .order_by(desc(Position.closed_at))
                    .limit(10)
                )
                positions = result.scalars().all()

                if not positions:
                    await query.message.reply_text("📭 No trading history yet")
                    return

                history_text = "📜 *Trading History*\n\n"

                for pos in positions[:5]:
                    pnl = float(pos.realized_pnl) if pos.realized_pnl else 0
                    emoji = "🟢" if pnl >= 0 else "🔴"

                    history_text += (
                        f"{emoji} *{pos.market_id[:15]}...*\n"
                        f"  • P&L: ${pnl:.2f}\n"
                        f"  • Closed: {pos.closed_at.strftime('%Y-%m-%d')}\n\n"
                    )

                await query.message.reply_text(history_text, parse_mode="Markdown")
        except Exception as e:
            await query.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def _cb_logs(self, query, user_id):
        """Callback for logs - sends new message."""
        if not await self.is_authorized(user_id):
            await query.message.reply_text("⛔ Not authorized")
            return

        try:
            async with async_session_maker() as db:
                from sqlalchemy import select, desc
                from void.data.models import Signal

                result = await db.execute(
                    select(Signal)
                    .order_by(desc(Signal.detected_at))
                    .limit(5)
                )
                signals = result.scalars().all()

                if not signals:
                    await query.message.reply_text("📭 No recent activity")
                    return

                logs_text = "📋 *Recent Activity*\n\n"

                for signal in signals:
                    status_emoji = {
                        "PENDING": "⏳",
                        "EXECUTED": "✅",
                        "SKIPPED": "⏭️",
                        "FAILED": "❌"
                    }.get(signal.status.value, "❓")

                    logs_text += (
                        f"{status_emoji} {signal.signal_type}\n"
                        f"  • Time: {signal.detected_at.strftime('%H:%M:%S')}\n\n"
                    )

                await query.message.reply_text(logs_text, parse_mode="Markdown")
        except Exception as e:
            await query.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def _cb_stats(self, query, user_id):
        """Callback for stats - sends new message."""
        if not await self.is_authorized(user_id):
            await query.message.reply_text("⛔ Not authorized")
            return

        try:
            async with async_session_maker() as db:
                from sqlalchemy import select, func, desc

                total_positions = await db.execute(select(func.count(Position.id)))
                total_positions = total_positions.scalar() or 0

                closed_positions = await db.execute(
                    select(func.count(Position.id)).where(Position.is_closed == True)
                )
                closed_positions = closed_positions.scalar() or 0

                total_pnl = await db.execute(
                    select(func.sum(Position.realized_pnl)).where(Position.realized_pnl.isnot(None))
                )
                total_pnl = total_pnl.scalar() or 0

                stats_text = (
                    "📊 *Statistics*\n\n"
                    f"  • Total Positions: {total_positions}\n"
                    f"  • Closed: {closed_positions}\n"
                    f"  • Total P&L: ${float(total_pnl):.2f}\n"
                )

                await query.message.reply_text(stats_text, parse_mode="Markdown")
        except Exception as e:
            await query.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def _cb_settings(self, query, user_id):
        """Callback for settings - shows settings menu."""
        if not await self.is_admin(user_id):
            await query.message.reply_text("⛔ Admin privileges required")
            return

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = [
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_back")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_text(
            "⚙️ *Settings*\n\nSettings menu coming soon!",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

    async def _cb_create_account(self, query, user_id):
        """Callback for create account."""
        if not await self.is_admin(user_id):
            await query.message.reply_text("⛔ Admin privileges required")
            return

        try:
            from void.accounts.service import AccountService
            from eth_account import Account
            from datetime import datetime

            async with async_session_maker() as db:
                service = AccountService(db)

                account_name = f"account-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                acct = Account.create()
                private_key = acct.key.hex()

                account = await service.create_account(
                    name=account_name,
                    private_key=private_key,
                )

                await db.commit()
                await db.refresh(account)

                message = f"""
✅ *Account Created!*

🏦 *Details:*
  • Name: {account.name}
  • Address: `{account.address}`

🔐 *PRIVATE KEY - SAVE NOW:*
`{private_key}`

⚠️ Save this private key - you won't see it again!
"""

                await query.message.reply_text(message, parse_mode="Markdown")
        except Exception as e:
            await query.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def _cb_create_agent(self, query, user_id):
        """Callback for create agent."""
        if not await self.is_admin(user_id):
            await query.message.reply_text("⛔ Admin privileges required")
            return

        try:
            from void.data.models import StrategyType
            from datetime import datetime

            async with async_session_maker() as db:
                from sqlalchemy import select
                result = await db.execute(select(Account).limit(1))
                account = result.scalar_one_or_none()

                if not account:
                    await query.message.reply_text("❌ No account found. Create one first.")
                    return

                agent = Agent(
                    name=f"agent-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                    status=AgentStatus.IDLE,
                    account_id=account.id,
                    strategy_type=StrategyType.ORACLE_LATENCY,
                    strategy_config={
                        "max_position_size_usd": "500",
                        "max_positions": 3,
                    },
                    max_position_size=500,
                    max_daily_loss=100,
                    max_concurrent_positions=3,
                )

                db.add(agent)
                await db.commit()

                message = (
                    f"✅ Agent Created!\n\n"
                    f"  • Name: {agent.name}\n"
                    f"  • ID: {agent.id}\n"
                    f"  • Strategy: {agent.strategy_type.value}"
                )

                await query.message.reply_text(message)
        except Exception as e:
            await query.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def _cb_remove_account(self, query, user_id):
        """Callback for remove account - shows account selection."""
        if not await self.is_admin(user_id):
            await query.message.reply_text("⛔ Admin privileges required")
            return

        try:
            async with async_session_maker() as db:
                from sqlalchemy import select

                result = await db.execute(select(Account))
                accounts = result.scalars().all()

                if not accounts:
                    await query.message.reply_text("📭 No accounts found")
                    return

                # Create inline keyboard with account options
                keyboard = []
                for acc in accounts[:10]:  # Max 10 accounts
                    keyboard.append([
                        InlineKeyboardButton(
                            f"🗑️ {acc.name} ({acc.address[:10]}...)",
                            callback_data=f"remove_account_{acc.id}"
                        )
                    ])

                keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="menu_cancel")])

                reply_markup = InlineKeyboardMarkup(keyboard)

                message = f"""
🗑️ *Remove Account*

⚠️ *WARNING: This action is irreversible!*

Select an account to remove:

*Accounts ({len(accounts)}):*
"""

                await query.message.reply_text(
                    message,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
        except Exception as e:
            await query.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def _handle_remove_account(self, query, user_id, action):
        """Handle actual account removal with confirmation."""
        if not await self.is_admin(user_id):
            await query.message.reply_text("⛔ Admin privileges required")
            return

        try:
            # Extract account ID from callback data
            account_id = action.split("_")[-1]

            from void.accounts.service import AccountService

            async with async_session_maker() as db:
                from sqlalchemy import select
                from uuid import UUID

                result = await db.execute(select(Account).where(Account.id == UUID(account_id)))
                account = result.scalar_one_or_none()

                if not account:
                    await query.message.reply_text("❌ Account not found")
                    return

                # Check if account has balance
                if float(account.usdc_balance or 0) > 0 or float(account.matic_balance or 0) > 0:
                    await query.message.reply_text(
                        f"⚠️ *Cannot remove account with balance!*\n\n"
                        f"Please withdraw all funds first:\n"
                        f"  • USDC: ${float(account.usdc_balance or 0):.2f}\n"
                        f"  • MATIC: {float(account.matic_balance or 0):.4f}",
                        parse_mode="Markdown"
                    )
                    return

                # Check for associated agents and positions
                from void.data.models import Agent, Position

                agents_result = await db.execute(
                    select(Agent).where(Agent.account_id == UUID(account_id))
                )
                agents_count = len(agents_result.scalars().all())

                positions_result = await db.execute(
                    select(Position).where(Position.account_id == UUID(account_id))
                )
                positions_count = len(positions_result.scalars().all())

                # Create confirmation keyboard
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "✅ Yes, delete permanently",
                            callback_data=f"confirm_remove_{account_id}"
                        ),
                        InlineKeyboardButton("❌ No, cancel", callback_data="menu_cancel")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                warning_message = f"""
⚠️ *CONFIRM ACCOUNT DELETION*

You are about to permanently delete:

  • Name: {account.name}
  • Address: `{account.address}`
  • USDC Balance: ${float(account.usdc_balance or 0):.2f}
  • MATIC Balance: {float(account.matic_balance or 0):.4f}

*Associated data to be deleted:*
  • Agents: {agents_count}
  • Positions: {positions_count}

🚨 *This action CANNOT be undone!*

Make sure you have saved your private key before deleting.

*Do you want to proceed?*
"""

                await query.message.reply_text(
                    warning_message,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )

        except Exception as e:
            logger.error(f"Handle remove account error: {e}", exc_info=True)
            await query.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def _confirm_remove_account(self, query, user_id, action):
        """Execute account removal after confirmation."""
        if not await self.is_admin(user_id):
            await query.message.reply_text("⛔ Admin privileges required")
            return

        try:
            # Extract account ID from callback data
            account_id = action.split("_")[-1]

            from void.accounts.service import AccountService

            async with async_session_maker() as db:
                from sqlalchemy import select
                from uuid import UUID

                result = await db.execute(select(Account).where(Account.id == UUID(account_id)))
                account = result.scalar_one_or_none()

                if not account:
                    await query.message.reply_text("❌ Account not found")
                    return

                account_name = account.name
                account_address = account.address

                # Delete the account
                service = AccountService(db)
                await service.delete_account(UUID(account_id))

                success_message = f"""
✅ *Account Deleted Successfully*

Deleted account:
  • Name: {account_name}
  • Address: `{account_address}`

⚠️ *Reminder:*
All data for this account has been permanently removed from the system.
We hope you saved your private key!

*Remaining accounts can be viewed with* /portfolio
"""

                await query.message.reply_text(success_message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Confirm remove account error: {e}", exc_info=True)
            await query.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def _cb_deposit(self, query, user_id):
        """Callback for deposit."""
        if not await self.is_authorized(user_id):
            await query.message.reply_text("⛔ Not authorized")
            return

        try:
            async with async_session_maker() as db:
                from sqlalchemy import select

                result = await db.execute(select(Account).limit(1))
                account = result.scalar_one_or_none()

                if not account:
                    await query.message.reply_text("❌ No account found")
                    return

                message = (
                    f"💰 *Deposit*\n\n"
                    f"Address: `{account.address}`\n\n"
                    f"Send USDC (Polygon) to fund your account."
                )

                await query.message.reply_text(message, parse_mode="Markdown")
        except Exception as e:
            await query.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def _cb_withdraw(self, query, user_id):
        """Callback for withdraw."""
        if not await self.is_admin(user_id):
            await query.message.reply_text("⛔ Admin privileges required")
            return

        message = (
            "💸 *Withdrawal*\n\n"
            "Withdrawals are done manually on Polymarket.exchange\n\n"
            "1. Close positions\n"
            "2. Connect wallet on Polymarket\n"
            "3. Withdraw funds"
        )

        await query.message.reply_text(message, parse_mode="Markdown")

    async def _cb_sync(self, query, user_id):
        """Callback for sync balances."""
        if not await self.is_admin(user_id):
            await query.message.reply_text("⛔ Admin privileges required")
            return

        try:
            from void.bot.utils import get_polygon_balance

            async with async_session_maker() as db:
                from sqlalchemy import select

                result = await db.execute(select(Account))
                accounts = result.scalars().all()

                if not accounts:
                    await query.message.reply_text("❌ No accounts found")
                    return

                sync_text = "🔄 *Syncing Balances*\n\n"

                for account in accounts:
                    old_usdc = float(account.usdc_balance or 0)
                    old_matic = float(account.matic_balance or 0)

                    usdc = await get_polygon_balance(account.address, "usdc")
                    matic = await get_polygon_balance(account.address, "matic")

                    account.usdc_balance = str(usdc)
                    account.matic_balance = str(matic)

                    await db.commit()

                    sync_text += (
                        f"✅ {account.address[:10]}...\n"
                        f"  USDC: ${old_usdc:.2f} → ${usdc:.2f}\n"
                        f"  MATIC: {old_matic:.4f} → {matic:.4f}\n\n"
                    )

                await query.message.reply_text(sync_text, parse_mode="Markdown")
        except Exception as e:
            await query.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def about(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /about command."""
        about_text = (
            "🤖 *About VOID*\n\n"
            "VOID is an autonomous trading agent for Polymarket prediction markets.\n\n"
            "*Version:* 1.0.0\n"
            "*Strategy:* Oracle Latency Arbitrage\n"
            "*AI Model:* Z.ai GLM-4.7\n\n"
            "🚀 *Features:*\n"
            "• 24/7 automated trading\n"
            "• AI-powered outcome verification\n"
            "• Real-time market scanning\n"
            "• Risk management\n"
            "• Portfolio tracking\n\n"
            "Built with ❤️ using Python and Telegram Bot API"
        )

        await update.message.reply_text(about_text, parse_mode="Markdown")

    # ============== Advanced Management Commands ==============

    async def start_agent(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start_agent command - Start a trading agent."""
        user_id = update.effective_user.id

        if not await self.is_admin(user_id):
            await update.message.reply_text("⛔ Admin privileges required")
            return

        try:
            # Get agent identifier from args
            if not context.args or len(context.args) < 1:
                await update.message.reply_text(
                    "❌ Usage: /start_agent <agent_name_or_id>\n\n"
                    "Use /agents to see available agents."
                )
                return

            agent_identifier = context.args[0]

            async with async_session_maker() as db:
                from sqlalchemy import select, or_

                # Try to find agent - first try by name (easiest)
                result = await db.execute(
                    select(Agent).where(Agent.name == agent_identifier)
                )
                agent = result.scalar_one_or_none()

                # If not found by name, try by ID (as UUID)
                if not agent:
                    try:
                        from uuid import UUID
                        agent_uuid = UUID(agent_identifier)
                        result = await db.execute(
                            select(Agent).where(Agent.id == agent_uuid)
                        )
                        agent = result.scalar_one_or_none()
                    except ValueError:
                        # Not a valid UUID, already tried by name
                        pass

                if not agent:
                    await update.message.reply_text(f"❌ Agent '{agent_identifier}' not found")
                    return

                # Update agent status
                agent.status = AgentStatus.RUNNING
                agent.last_heartbeat = datetime.now(timezone.utc)
                await db.commit()

                message = (
                    f"✅ Agent Started!\n\n"
                    f"🤖 Agent: {agent.name}\n"
                    f"  • Strategy: {agent.strategy_type.value}\n"
                    f"  • Status: {agent.status.value}\n\n"
                    f"🚀 Agent is now scanning for opportunities..."
                )
                await update.message.reply_text(message)

        except Exception as e:
            logger.error(f"Start agent error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error starting agent: {str(e)[:100]}")

    async def stop_agent(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop_agent command - Stop a trading agent."""
        user_id = update.effective_user.id

        if not await self.is_admin(user_id):
            await update.message.reply_text("⛔ Admin privileges required")
            return

        try:
            if not context.args or len(context.args) < 1:
                await update.message.reply_text(
                    "❌ Usage: /stop_agent <agent_name_or_id>\n\n"
                    "Use /agents to see available agents."
                )
                return

            agent_identifier = context.args[0]

            async with async_session_maker() as db:
                from sqlalchemy import select

                # Try to find agent - first try by name (easiest)
                result = await db.execute(
                    select(Agent).where(Agent.name == agent_identifier)
                )
                agent = result.scalar_one_or_none()

                # If not found by name, try by ID (as UUID)
                if not agent:
                    try:
                        from uuid import UUID
                        agent_uuid = UUID(agent_identifier)
                        result = await db.execute(
                            select(Agent).where(Agent.id == agent_uuid)
                        )
                        agent = result.scalar_one_or_none()
                    except ValueError:
                        # Not a valid UUID, already tried by name
                        pass

                if not agent:
                    await update.message.reply_text(f"❌ Agent '{agent_identifier}' not found")
                    return

                # Update agent status
                agent.status = AgentStatus.STOPPED
                await db.commit()

                message = (
                    f"⏹️ Agent Stopped\n\n"
                    f"🤖 Agent: {agent.name}\n"
                    f"  • Status: {agent.status.value}\n\n"
                    f"Agent will complete existing trades and stop scanning."
                )
                await update.message.reply_text(message)

        except Exception as e:
            logger.error(f"Stop agent error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error stopping agent: {str(e)[:100]}")

    async def delete_agent(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /delete_agent command - Delete a trading agent permanently."""
        user_id = update.effective_user.id

        if not await self.is_admin(user_id):
            await update.message.reply_text("⛔ Admin privileges required")
            return

        try:
            if not context.args or len(context.args) < 1:
                await update.message.reply_text(
                    "❌ Usage: /delete_agent <agent_name_or_id>\n\n"
                    "Use /agents to see available agents."
                )
                return

            agent_identifier = context.args[0]

            async with async_session_maker() as db:
                from sqlalchemy import select

                # Try to find agent - first try by name (easiest)
                result = await db.execute(
                    select(Agent).where(Agent.name == agent_identifier)
                )
                agent = result.scalar_one_or_none()

                # If not found by name, try by ID (as UUID)
                if not agent:
                    try:
                        from uuid import UUID
                        agent_uuid = UUID(agent_identifier)
                        result = await db.execute(
                            select(Agent).where(Agent.id == agent_uuid)
                        )
                        agent = result.scalar_one_or_none()
                    except ValueError:
                        # Not a valid UUID, already tried by name
                        pass

                if not agent:
                    await update.message.reply_text(f"❌ Agent '{agent_identifier}' not found")
                    return

                agent_name = agent.name

                # Delete agent
                await db.delete(agent)
                await db.commit()

                message = (
                    f"✅ Agent Deleted\n\n"
                    f"🤖 Deleted agent: {agent_name}\n\n"
                    f"Agent has been permanently removed."
                )
                await update.message.reply_text(message)

        except Exception as e:
            logger.error(f"Delete agent error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error deleting agent: {str(e)[:100]}")

    async def close_position(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /close_position command - Close a specific position."""
        user_id = update.effective_user.id

        if not await self.is_admin(user_id):
            await update.message.reply_text("⛔ Admin privileges required")
            return

        try:
            if not context.args or len(context.args) < 1:
                await update.message.reply_text(
                    "❌ Usage: `/close_position <position_id>`\n\n"
                    "Use /positions to see open positions.",
                    parse_mode="Markdown"
                )
                return

            position_id = context.args[0]

            async with async_session_maker() as db:
                from sqlalchemy import select
                result = await db.execute(
                    select(Position).where(Position.id == position_id)
                )
                position = result.scalar_one_or_none()

                if not position:
                    await update.message.reply_text("❌ Position not found")
                    return

                if position.is_closed:
                    await update.message.reply_text("⚠️ Position is already closed")
                    return

                # Mark position as closed
                position.is_closed = True
                position.closed_at = datetime.now(timezone.utc)
                await db.commit()

                pnl = float(position.unrealized_pnl) if position.unrealized_pnl else 0
                pnl_emoji = "🟢" if pnl >= 0 else "🔴"

                message = (
                    f"✅ *Position Closed*\n\n"
                    f"📊 *Position Details:*\n"
                    f"  • Market: {position.market_id[:20]}...\n"
                    f"  • Side: {position.side}\n"
                    f"  • Size: ${float(position.size):.2f}\n"
                    f"  • Entry: {float(position.avg_entry_price):.4f}\n\n"
                    f"{pnl_emoji} *P&L:* ${pnl:.2f}\n\n"
                    f"⚠️ Note: You still need to exit on Polymarket"
                )
                await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Close position error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error closing position: {str(e)[:100]}")

    async def history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /history command - Show trading history."""
        user_id = update.effective_user.id

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        try:
            async with async_session_maker() as db:
                from sqlalchemy import select, desc

                # Get closed positions
                result = await db.execute(
                    select(Position)
                    .where(Position.is_closed == True)
                    .order_by(desc(Position.closed_at))
                    .limit(20)
                )
                positions = result.scalars().all()

                if not positions:
                    await update.message.reply_text("📭 No closed positions yet")
                    return

                history_text = "📜 *Trading History*\n\n"

                total_pnl = 0
                wins = 0
                losses = 0

                for pos in positions[:10]:
                    pnl = float(pos.realized_pnl) if pos.realized_pnl else 0
                    total_pnl += pnl
                    if pnl >= 0:
                        wins += 1
                        emoji = "🟢"
                    else:
                        losses += 1
                        emoji = "🔴"

                    history_text += (
                        f"{emoji} *{pos.market_id[:15]}...*\n"
                        f"  • Side: {pos.side} | Size: ${float(pos.size):.2f}\n"
                        f"  • P&L: ${pnl:.2f}\n"
                        f"  • Closed: {pos.closed_at.strftime('%Y-%m-%d %H:%M')}\n\n"
                    )

                win_rate = (wins / len(positions)) * 100 if positions else 0

                history_text += (
                    f"📊 *Summary:*\n"
                    f"  • Total Trades: {len(positions)}\n"
                    f"  • Wins: {wins} | Losses: {losses}\n"
                    f"  • Win Rate: {win_rate:.1f}%\n"
                    f"  • Total P&L: ${total_pnl:.2f}"
                )

                await update.message.reply_text(history_text, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"History error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error retrieving history: {str(e)[:100]}")

    async def logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /logs command - Show recent system logs."""
        user_id = update.effective_user.id

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        try:
            async with async_session_maker() as db:
                from sqlalchemy import select, desc
                from void.data.models import Signal

                # Get recent signals
                result = await db.execute(
                    select(Signal)
                    .order_by(desc(Signal.detected_at))
                    .limit(10)
                )
                signals = result.scalars().all()

                if not signals:
                    await update.message.reply_text("📭 No recent signals")
                    return

                logs_text = "📋 *Recent Activity*\n\n"

                for signal in signals[:5]:
                    confidence = f"{float(signal.confidence)*100:.0f}%" if signal.confidence else "N/A"
                    status_emoji = {
                        "PENDING": "⏳",
                        "EXECUTED": "✅",
                        "SKIPPED": "⏭️",
                        "FAILED": "❌"
                    }.get(signal.status.value, "❓")

                    logs_text += (
                        f"{status_emoji} *Signal: {signal.signal_type}*\n"
                        f"  • Market: {signal.market_id[:15]}...\n"
                        f"  • Confidence: {confidence}\n"
                        f"  • Time: {signal.detected_at.strftime('%H:%M:%S')}\n\n"
                    )

                await update.message.reply_text(logs_text, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Logs error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error retrieving logs: {str(e)[:100]}")

    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command - Show settings menu."""
        user_id = update.effective_user.id

        if not await self.is_admin(user_id):
            await update.message.reply_text("⛔ Admin privileges required")
            return

        keyboard = [
            [InlineKeyboardButton("🔔 Notifications", callback_data="settings_notifications")],
            [InlineKeyboardButton("⚠️ Risk Limits", callback_data="settings_risk")],
            [InlineKeyboardButton("🔄 Auto Sync", callback_data="settings_sync")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_main")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "⚙️ *Settings Menu*\n\nConfigure your bot settings:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

    async def deposit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /deposit command - Show deposit address and info."""
        user_id = update.effective_user.id

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        try:
            async with async_session_maker() as db:
                from sqlalchemy import select

                result = await db.execute(
                    select(Account).order_by(Account.created_at).limit(1)
                )
                account = result.scalar_one_or_none()

                if not account:
                    await update.message.reply_text(
                        "❌ No account found. Create one with /create_account"
                    )
                    return

                message = (
                    f"💰 *Deposit Information*\n\n"
                    f"🏦 *Wallet Address:*\n`{account.address}`\n\n"
                    f"📝 *Instructions:*\n"
                    f"  • Send USDC (Polygon) to the address above\n"
                    f"  • Minimum deposit: 10 USDC\n"
                    f"  • Use Polygon network (not Ethereum)\n"
                    f"  • Transaction will appear after confirmation\n\n"
                    f"🔄 Use /sync to check for deposits after sending"
                )

                await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Deposit info error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def withdraw(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /withdraw command - Show withdraw instructions."""
        user_id = update.effective_user.id

        if not await self.is_admin(user_id):
            await update.message.reply_text("⛔ Admin privileges required")
            return

        message = (
            "💸 *Withdrawal Guide*\n\n"
            "⚠️ *Important Security Notes:*\n"
            "  • Withdrawals are done manually on Polymarket\n"
            "  • Bot can close positions but cannot withdraw funds\n"
            "  • Never share your private key\n\n"
            "📝 *Steps:*\n"
            "  1. Close all positions with /close_position\n"
            "  2. Go to Polymarket.exchange\n"
            "  3. Connect your wallet\n"
            "  4. Withdraw to your destination address\n\n"
            f"💡 Use /portfolio to check current balance"
        )

        await update.message.reply_text(message, parse_mode="Markdown")

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command - Show detailed statistics."""
        user_id = update.effective_user.id

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        try:
            async with async_session_maker() as db:
                from sqlalchemy import select, func, desc

                # Get statistics
                total_positions = await db.execute(
                    select(func.count(Position.id))
                )
                total_positions = total_positions.scalar() or 0

                closed_positions = await db.execute(
                    select(func.count(Position.id)).where(Position.is_closed == True)
                )
                closed_positions = closed_positions.scalar() or 0

                total_pnl = await db.execute(
                    select(func.sum(Position.realized_pnl)).where(Position.realized_pnl.isnot(None))
                )
                total_pnl = total_pnl.scalar() or 0

                # Best trade
                best_trade = await db.execute(
                    select(Position)
                    .where(Position.is_closed == True)
                    .order_by(desc(Position.realized_pnl))
                    .limit(1)
                )
                best_trade = best_trade.scalar_one_or_none()

                # Worst trade
                worst_trade = await db.execute(
                    select(Position)
                    .where(Position.is_closed == True)
                    .order_by(Position.realized_pnl)
                    .limit(1)
                )
                worst_trade = worst_trade.scalar_one_or_none()

                stats_text = (
                    "📊 *Performance Statistics*\n\n"
                    f"📈 *Trading Overview:*\n"
                    f"  • Total Positions: {total_positions}\n"
                    f"  • Closed Positions: {closed_positions}\n"
                    f"  • Open Positions: {total_positions - closed_positions}\n\n"
                )

                if total_pnl != 0:
                    pnl_emoji = "🟢" if total_pnl > 0 else "🔴"
                    stats_text += f"{pnl_emoji} *Total P&L:* ${float(total_pnl):.2f}\n\n"

                if best_trade:
                    stats_text += (
                        f"🏆 *Best Trade:*\n"
                        f"  • P&L: ${float(best_trade.realized_pnl):.2f}\n"
                        f"  • Market: {best_trade.market_id[:20]}...\n\n"
                    )

                if worst_trade:
                    stats_text += (
                        f"📉 *Worst Trade:*\n"
                        f"  • P&L: ${float(worst_trade.realized_pnl):.2f}\n"
                        f"  • Market: {worst_trade.market_id[:20]}...\n\n"
                    )

                await update.message.reply_text(stats_text, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Stats error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error retrieving stats: {str(e)[:100]}")

    # ============== Notification Methods ==============

    async def notify_signal(self, signal: Signal):
        """Send notification when signal is detected."""
        if not self.config.notify_on_signal:
            return

        confidence = f"{float(signal.confidence)*100:.0f}%" if signal.confidence else "N/A"
        profit = f"{float(signal.profit_margin)*100:.1f}%" if signal.profit_margin else "N/A"

        message = (
            f"🚨 *New Signal Detected!*\n\n"
            f"🎯 *Market:* {signal.market_id[:10]}...\n"
            f"  • Type: {signal.signal_type}\n"
            f"  • Outcome: {signal.predicted_outcome}\n"
            f"  • Confidence: {confidence}\n"
            f"  • Profit: {profit}\n"
            f"  • Time: {signal.detected_at.strftime('%H:%M:%S')}\n\n"
            f"Strategy: {signal.strategy_type}"
        )

        # Send to all allowed users
        # Implementation depends on how you want to handle broadcasting
        # For now, log it
        struct_logger.info("telegram_signal_notification", message=message)

    async def notify_trade(self, position: Position):
        """Send notification when trade is executed."""
        if not self.config.notify_on_trade:
            return

        message = (
            f"💼 *Trade Executed!*\n\n"
            f"🎯 *Market:* {position.market_id[:10]}...\n"
            f"  • Side: {position.side}\n"
            f"  • Size: ${float(position.size_usd):.2f}\n"
            f"  • Entry: {float(position.entry_price):.4f}\n"
            f"  • Time: {position.entered_at.strftime('%H:%M:%S')}\n\n"
            f"Position ID: {str(position.id)[:8]}..."
        )

        struct_logger.info("telegram_trade_notification", message=message)

    async def notify_error(self, error_message: str):
        """Send notification on error."""
        if not self.config.notify_on_error:
            return

        message = (
            f"⚠️ *VOID Error*\n\n"
            f"```\n{error_message}\n```\n\n"
            f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

        struct_logger.info("telegram_error_notification", message=message)

    # ============== Bot Lifecycle ==============

    def setup_handlers(self):
        """Setup bot handlers."""
        # Basic commands
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("about", self.about))

        # Monitoring commands
        self.application.add_handler(CommandHandler("status", self.status))
        self.application.add_handler(CommandHandler("portfolio", self.portfolio))
        self.application.add_handler(CommandHandler("positions", self.positions))
        self.application.add_handler(CommandHandler("signals", self.signals))
        self.application.add_handler(CommandHandler("agents", self.agents))
        self.application.add_handler(CommandHandler("agent", self.agent_control))
        self.application.add_handler(CommandHandler("history", self.history))
        self.application.add_handler(CommandHandler("logs", self.logs))
        self.application.add_handler(CommandHandler("stats", self.stats))

        # Management commands
        self.application.add_handler(CommandHandler("menu", self.menu))
        self.application.add_handler(CommandHandler("settings", self.settings))
        self.application.add_handler(CommandHandler("create_account", self.create_account))
        self.application.add_handler(CommandHandler("remove_account", self.remove_account))
        self.application.add_handler(CommandHandler("create_agent", self.create_agent))
        self.application.add_handler(CommandHandler("sync", self.sync_balances))

        # Admin commands
        self.application.add_handler(CommandHandler("start_agent", self.start_agent))
        self.application.add_handler(CommandHandler("stop_agent", self.stop_agent))
        self.application.add_handler(CommandHandler("delete_agent", self.delete_agent))
        self.application.add_handler(CommandHandler("close_position", self.close_position))
        self.application.add_handler(CommandHandler("deposit", self.deposit))
        self.application.add_handler(CommandHandler("withdraw", self.withdraw))

        # Callback handlers
        self.application.add_handler(CallbackQueryHandler(self.button_callback, pattern='^(start|stop)_'))
        self.application.add_handler(CallbackQueryHandler(self.menu_callback, pattern='^menu_'))
        self.application.add_handler(CallbackQueryHandler(self.menu_callback, pattern='^settings_'))
        self.application.add_handler(CallbackQueryHandler(self.menu_callback, pattern='^remove_account_'))
        self.application.add_handler(CallbackQueryHandler(self.menu_callback, pattern='^confirm_remove_'))
        self.application.add_handler(CallbackQueryHandler(self.menu_callback, pattern='^menu_cancel'))

    async def setup_menu_button(self):
        """Set up bot menu button using Bot API."""
        try:
            from telegram import BotCommandScopeAllPrivateChats, BotCommand
            from telegram import MenuButtonCommands

            # Set menu button to show commands
            await self.application.bot.set_chat_menu_button(
                menu_button=MenuButtonCommands()
            )

            # Set up command list for the menu
            commands = [
                BotCommand("menu", "🎛️ Main menu"),
                BotCommand("status", "📊 System status"),
                BotCommand("portfolio", "💰 Portfolio"),
                BotCommand("agents", "🤖 Trading agents"),
                BotCommand("positions", "📈 Open positions"),
                BotCommand("history", "📜 Trading history"),
                BotCommand("stats", "📊 Performance stats"),
                BotCommand("help", "❓ Help & commands"),
            ]

            await self.application.bot.set_my_commands(
                commands,
                scope=BotCommandScopeAllPrivateChats()
            )

            logger.info("✅ Bot menu button configured")
        except Exception as e:
            logger.error(f"Failed to set up menu button: {e}", exc_info=True)

    async def start_polling(self):
        """Start bot polling."""
        """Create application and start polling."""
        self.application = Application.builder().token(self.config.token).build()

        self.setup_handlers()

        await self.application.initialize()
        await self.application.start()

        # Set up bot menu button
        await self.setup_menu_button()

        await self.application.updater.start_polling(drop_pending_updates=True)

        logger.info("🤖 VOID Bot started polling")

    async def stop(self):
        """Stop bot."""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            logger.info("🤖 VOID Bot stopped")

    async def run_webhook(self, webhook_url: str):
        """Run bot with webhook."""
        self.application = Application.builder().token(self.config.token).build()

        self.setup_handlers()

        await self.application.initialize()
        await self.application.start()

        # Set webhook
        await self.application.bot.set_webhook(webhook_url)

        logger.info(f"🤖 VOID Bot started with webhook: {webhook_url}")
