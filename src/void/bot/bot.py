"""
VOID Telegram Bot - Main bot implementation.

Provides Telegram interface for controlling and monitoring VOID trading agent.
"""

import asyncio
import io
import logging
from datetime import datetime, timezone
from typing import Optional

import qrcode
from PIL import Image

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
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
from void.data.models import Agent, Account, Position, Signal, AgentStatus, Market
from void.accounts.service import AccountService
from void.agent.orchestrator import AgentOrchestrator
from void.messaging import EventBus
from void.messaging.events import EventType
from void.ai.chat_service import ChatService
from void.data.knowledge.service import KnowledgeService
from void.data.feeds.twitter_collector import TwitterCollector
from void.tasks.scheduler import get_scheduler
from sqlalchemy import select, func
from void.config import config
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
        self.scheduler = get_scheduler()

        # Persistent agent management - keeps orchestrators alive
        self._running_agents: dict = {}  # agent_id -> {"orchestrator": ..., "task": ...}

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

    def is_private_chat(self, update: Update) -> bool:
        """Check if the message is from a private chat (not group)."""
        if update.effective_chat:
            return update.effective_chat.type == "private"
        return False

    async def require_private_chat(self, update: Update) -> bool:
        """
        Check if command is in private chat. If not, send warning and return False.
        Use this for commands that access personal/sensitive data.
        """
        if not self.is_private_chat(update):
            await update.message.reply_text(
                "🔒 This command contains personal data and only works in private chat.\n\n"
                "Please message me directly to use this feature."
            )
            return False
        return True

    def generate_deposit_qr(self, address: str) -> io.BytesIO:
        """
        Generate a QR code image for deposit address.

        Args:
            address: Wallet address to encode

        Returns:
            BytesIO buffer containing PNG image
        """
        # Create QR code with high error correction
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(address)
        qr.make(fit=True)

        # Create image with dark purple color scheme
        img = qr.make_image(fill_color="#1a1a2e", back_color="white")

        # Save to bytes buffer
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        return buffer

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

*🤖 AI Assistant (NEW!):*
/ask <question> - Ask AI anything about your portfolio
/research <market_id> - AI-powered market research
/trends - View Twitter trends
/news - Latest market news
💡 Or just type any question directly!

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
/go_live - Enable live trading
/go_dry - Switch to dry-run mode
/agent_config - View agent settings
/agent - Quick agent control

*⚙️ Settings:*
/settings - Configure bot settings

*❓ Other:*
/close_position - Close a position
/about - About VOID

💡 Use /menu for easy navigation!
💡 Try typing "What's my portfolio status?" directly!
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

        # Require private chat for sensitive financial data
        if not await self.require_private_chat(update):
            return

        async with async_session_maker() as db:
            # Filter by user's telegram_user_id
            result = await db.execute(
                select(Account).where(Account.telegram_user_id == user_id)
            )
            accounts = result.scalars().all()

        if not accounts:
            await update.message.reply_text(
                "📊 No accounts found.\n\n"
                "Use /create_account to create your first trading account."
            )
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

        # Require private chat for sensitive financial data
        if not await self.require_private_chat(update):
            return

        try:
            async with async_session_maker() as db:
                # Get user's accounts first
                accounts_result = await db.execute(
                    select(Account.id).where(Account.telegram_user_id == user_id)
                )
                user_account_ids = [row[0] for row in accounts_result.fetchall()]

                if not user_account_ids:
                    await update.message.reply_text("📊 No accounts found. Create one with /create_account")
                    return

                # Get positions only for user's accounts
                result = await db.execute(
                    select(Position)
                    .where(
                        Position.is_closed == False,
                        Position.account_id.in_(user_account_ids)
                    )
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

        # Require private chat for sensitive data
        if not await self.require_private_chat(update):
            return

        async with async_session_maker() as db:
            # Filter by user's telegram_user_id
            result = await db.execute(
                select(Agent)
                .where(Agent.telegram_user_id == user_id)
                .order_by(Agent.created_at.desc())
            )
            agents = result.scalars().all()

        if not agents:
            await update.message.reply_text(
                "🤖 No agents found.\n\n"
                "Use /create_agent to create your first trading agent."
            )
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

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        # Require private chat for sensitive key display
        if not await self.require_private_chat(update):
            return

        try:
            from void.accounts.service import AccountService
            from eth_account import Account as EthAccount
            from datetime import datetime

            async with async_session_maker() as db:
                service = AccountService(db)

                # Generate new wallet
                account_name = f"account-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                acct = EthAccount.create()
                private_key = acct.key.hex()

                # Create account with user's telegram_user_id
                account = await service.create_account(
                    name=account_name,
                    telegram_user_id=user_id,
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
  • Use this key to import wallet into MetaMask

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

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        # Require private chat for sensitive operations
        if not await self.require_private_chat(update):
            return

        try:
            async with async_session_maker() as db:
                from sqlalchemy import select

                # Only get user's own accounts
                result = await db.execute(
                    select(Account).where(Account.telegram_user_id == user_id)
                )
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

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        # Require private chat
        if not await self.require_private_chat(update):
            return

        try:
            from void.data.models import StrategyType
            from datetime import datetime, timezone

            async with async_session_maker() as db:
                # Get user's first account
                from sqlalchemy import select
                result = await db.execute(
                    select(Account)
                    .where(Account.telegram_user_id == user_id)
                    .limit(1)
                )
                account = result.scalar_one_or_none()

                if not account:
                    await update.message.reply_text(
                        "❌ No accounts found. Create one first with /create_account"
                    )
                    return

                # Create agent with user's telegram_user_id
                agent = Agent(
                    telegram_user_id=user_id,
                    name=f"agent-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                    status=AgentStatus.IDLE,
                    account_id=account.id,
                    strategy_type=StrategyType.ORACLE_LATENCY,
                    strategy_config={
                        # Capital allocation
                        "max_position_size_usd": "500",
                        "max_positions": 3,
                        # Risk parameters
                        "min_profit_margin": "0.01",
                        "max_slippage": "0.02",
                        # Oracle latency specific
                        "min_discount": "0.01",
                        "max_price": "0.99",
                        "max_hours_since_end": 24,
                        "min_hours_since_end": 0,
                        # AI verification
                        "use_ai_verification": True,
                        "ai_confidence_threshold": "0.85",
                        "verification_timeout_seconds": 30,
                        # Filters
                        "min_liquidity_usd": "1000",
                        "min_volume_24h_usd": "5000",
                        # Timing
                        "scan_interval_seconds": 30,
                        # Safety - dry run by default
                        "dry_run": True,
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
                    f"  • Name: `{agent.name}`\n"
                    f"  • Strategy: Oracle Latency\n"
                    f"  • Account: {account.name}\n"
                    f"  • Max Position: ${agent.max_position_size}\n"
                    f"  • AI Verification: ✅ Enabled\n"
                    f"  • Mode: 🧪 DRY-RUN (no real trades)\n\n"
                    f"🚀 *Start the agent:*\n"
                    f"  `/start_agent {agent.name}`\n\n"
                    f"⚙️ To enable live trading, update config."
                )

                await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Create agent error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error creating agent: {str(e)[:100]}")

    async def sync_balances(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /sync command - Sync wallet balances from blockchain."""
        user_id = update.effective_user.id

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        # Require private chat
        if not await self.require_private_chat(update):
            return

        try:
            from void.accounts.service import AccountService

            async with async_session_maker() as db:
                service = AccountService(db)

                # Get only user's accounts
                from sqlalchemy import select
                result = await db.execute(
                    select(Account).where(Account.telegram_user_id == user_id)
                )
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

                # Get only user's accounts
                result = await db.execute(
                    select(Account).where(Account.telegram_user_id == user_id)
                )
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

                # Get only user's agents
                result = await db.execute(
                    select(Agent).where(Agent.telegram_user_id == user_id)
                )
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

                # Get user's accounts first
                accounts_result = await db.execute(
                    select(Account.id).where(Account.telegram_user_id == user_id)
                )
                user_account_ids = [row[0] for row in accounts_result.fetchall()]

                if not user_account_ids:
                    await query.message.reply_text("📭 No accounts found")
                    return

                # Get positions only for user's accounts
                result = await db.execute(
                    select(Position)
                    .where(
                        Position.is_closed == False,
                        Position.account_id.in_(user_account_ids)
                    )
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
        if not await self.is_authorized(user_id):
            await query.message.reply_text("⛔ Not authorized")
            return

        try:
            from void.accounts.service import AccountService
            from eth_account import Account as EthAccount
            from datetime import datetime

            async with async_session_maker() as db:
                service = AccountService(db)

                account_name = f"account-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                acct = EthAccount.create()
                private_key = acct.key.hex()

                # Create account with user's telegram_user_id
                account = await service.create_account(
                    name=account_name,
                    telegram_user_id=user_id,
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
        if not await self.is_authorized(user_id):
            await query.message.reply_text("⛔ Not authorized")
            return

        try:
            from void.data.models import StrategyType
            from datetime import datetime

            async with async_session_maker() as db:
                from sqlalchemy import select
                # Get user's first account
                result = await db.execute(
                    select(Account)
                    .where(Account.telegram_user_id == user_id)
                    .limit(1)
                )
                account = result.scalar_one_or_none()

                if not account:
                    await query.message.reply_text("❌ No account found. Create one first.")
                    return

                # Create agent with user's telegram_user_id
                agent = Agent(
                    telegram_user_id=user_id,
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
        if not await self.is_authorized(user_id):
            await query.message.reply_text("⛔ Not authorized")
            return

        try:
            async with async_session_maker() as db:
                from sqlalchemy import select

                # Only get user's own accounts
                result = await db.execute(
                    select(Account).where(Account.telegram_user_id == user_id)
                )
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
        if not await self.is_authorized(user_id):
            await query.message.reply_text("⛔ Not authorized")
            return

        try:
            # Extract account ID from callback data
            account_id = action.split("_")[-1]

            from void.accounts.service import AccountService

            async with async_session_maker() as db:
                from sqlalchemy import select
                from uuid import UUID

                # CRITICAL: Verify user owns this account
                result = await db.execute(
                    select(Account).where(
                        Account.id == UUID(account_id),
                        Account.telegram_user_id == user_id
                    )
                )
                account = result.scalar_one_or_none()

                if not account:
                    await query.message.reply_text("❌ Account not found or you don't have permission")
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
        if not await self.is_authorized(user_id):
            await query.message.reply_text("⛔ Not authorized")
            return

        try:
            # Extract account ID from callback data
            account_id = action.split("_")[-1]

            from void.accounts.service import AccountService

            async with async_session_maker() as db:
                from sqlalchemy import select
                from uuid import UUID

                # CRITICAL: Verify user owns this account
                result = await db.execute(
                    select(Account).where(
                        Account.id == UUID(account_id),
                        Account.telegram_user_id == user_id
                    )
                )
                account = result.scalar_one_or_none()

                if not account:
                    await query.message.reply_text("❌ Account not found or you don't have permission")
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

                # Get user's first account
                result = await db.execute(
                    select(Account)
                    .where(Account.telegram_user_id == user_id)
                    .limit(1)
                )
                account = result.scalar_one_or_none()

                if not account:
                    await query.message.reply_text("❌ No account found")
                    return

                # Generate QR code for address
                qr_buffer = self.generate_deposit_qr(account.address)

                caption = (
                    f"💰 *Deposit*\n\n"
                    f"🏦 *Address:*\n`{account.address}`\n\n"
                    f"📝 Send USDC (Polygon) to fund your account.\n\n"
                    f"🔄 Use /sync after sending"
                )

                await query.message.reply_photo(
                    photo=InputFile(qr_buffer, filename="deposit_qr.png"),
                    caption=caption,
                    parse_mode="Markdown"
                )
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
        if not await self.is_authorized(user_id):
            await query.message.reply_text("⛔ Not authorized")
            return

        try:
            from void.bot.utils import get_polygon_balance

            async with async_session_maker() as db:
                from sqlalchemy import select

                # Get only user's accounts
                result = await db.execute(
                    select(Account).where(Account.telegram_user_id == user_id)
                )
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

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        # Require private chat
        if not await self.require_private_chat(update):
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

                # Try to find agent by name - filter by user's agents only
                result = await db.execute(
                    select(Agent).where(
                        Agent.name == agent_identifier,
                        Agent.telegram_user_id == user_id
                    )
                )
                agent = result.scalar_one_or_none()

                # If not found by name, try by ID (as UUID)
                if not agent:
                    try:
                        from uuid import UUID
                        agent_uuid = UUID(agent_identifier)
                        result = await db.execute(
                            select(Agent).where(
                                Agent.id == agent_uuid,
                                Agent.telegram_user_id == user_id
                            )
                        )
                        agent = result.scalar_one_or_none()
                    except ValueError:
                        # Not a valid UUID, already tried by name
                        pass

                if not agent:
                    await update.message.reply_text(f"❌ Agent '{agent_identifier}' not found")
                    return

                # Check if agent is already running in our manager
                agent_id_str = str(agent.id)
                if agent_id_str in self._running_agents:
                    await update.message.reply_text(
                        f"⚠️ Agent {agent.name} is already running!\n\n"
                        f"Use /stop_agent {agent.name} first to restart it."
                    )
                    return

                # Update status in database first
                agent.status = AgentStatus.RUNNING
                agent.last_heartbeat = datetime.utcnow()
                await db.commit()
                await db.refresh(agent)

                # Send initial confirmation
                await update.message.reply_text(
                    f"🚀 Starting agent {agent.name}...\n"
                    f"Initializing market scanner..."
                )

            # Create and store the background task using shared scan loop method
            task = asyncio.create_task(
                self._create_agent_scan_loop(agent.id, agent.name, user_id)
            )
            self._running_agents[agent_id_str] = {
                "task": task,
                "name": agent.name,
                "started_at": datetime.utcnow()
            }

            await update.message.reply_text(
                f"✅ Agent Started!\n\n"
                f"🤖 Agent: {agent.name}\n"
                f"  • Strategy: {agent.strategy_type.value}\n"
                f"  • Status: RUNNING\n\n"
                f"🚀 Agent is now actively scanning markets!\n\n"
                f"The agent will:\n"
                f"  • Scan Polymarket every 30 seconds\n"
                f"  • Look for resolved events with price discrepancies\n"
                f"  • Log opportunities found\n\n"
                f"Use /agents to monitor status."
            )

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

                # Cancel the background task if running
                agent_id_str = str(agent.id)
                task_cancelled = False
                if agent_id_str in self._running_agents:
                    try:
                        self._running_agents[agent_id_str]["task"].cancel()
                        del self._running_agents[agent_id_str]
                        task_cancelled = True
                    except Exception as e:
                        logger.error(f"Error cancelling agent task: {e}")

                # Update agent status
                agent.status = AgentStatus.STOPPED
                await db.commit()

                status_note = "Scan loop cancelled." if task_cancelled else "Was not actively scanning."
                message = (
                    f"⏹️ Agent Stopped\n\n"
                    f"🤖 Agent: {agent.name}\n"
                    f"  • Status: {agent.status.value}\n"
                    f"  • {status_note}\n\n"
                    f"Agent will complete existing trades."
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

    async def go_live(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /go_live command - Enable live trading for an agent."""
        user_id = update.effective_user.id

        if not await self.is_admin(user_id):
            await update.message.reply_text("⛔ Admin privileges required")
            return

        try:
            if not context.args or len(context.args) < 1:
                await update.message.reply_text(
                    "❌ Usage: `/go_live <agent_name>`\n\n"
                    "⚠️ This enables REAL trading with real funds!\n\n"
                    "Use /agents to see available agents.",
                    parse_mode="Markdown"
                )
                return

            agent_identifier = context.args[0]

            async with async_session_maker() as db:
                # Try to find by name first, then by UUID if it looks like one
                from uuid import UUID as PyUUID
                try:
                    agent_uuid = PyUUID(agent_identifier)
                    result = await db.execute(
                        select(Agent).where(
                            (Agent.name == agent_identifier) |
                            (Agent.id == agent_uuid)
                        )
                    )
                except ValueError:
                    # Not a valid UUID, search by name only
                    result = await db.execute(
                        select(Agent).where(Agent.name == agent_identifier)
                    )
                agent = result.scalar_one_or_none()

                if not agent:
                    await update.message.reply_text(f"❌ Agent '{agent_identifier}' not found")
                    return

                # Update strategy config to disable dry_run
                # Create a new dict to ensure SQLAlchemy detects the change
                config = dict(agent.strategy_config or {})
                config["dry_run"] = False
                agent.strategy_config = config
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(agent, "strategy_config")
                await db.commit()

                message = (
                    f"🔴 *LIVE TRADING ENABLED*\n\n"
                    f"🤖 Agent: {agent.name}\n"
                    f"💰 Mode: *LIVE* (real trades)\n\n"
                    f"⚠️ *Warning:* Agent will now execute real trades!\n\n"
                    f"💡 Use `/go_dry {agent.name}` to switch back to dry-run mode.\n"
                    f"🔄 Restart agent with `/stop_agent` then `/start_agent` to apply."
                )
                await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Go live error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def go_dry(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /go_dry command - Enable dry-run mode for an agent."""
        user_id = update.effective_user.id

        if not await self.is_admin(user_id):
            await update.message.reply_text("⛔ Admin privileges required")
            return

        try:
            if not context.args or len(context.args) < 1:
                await update.message.reply_text(
                    "❌ Usage: `/go_dry <agent_name>`\n\n"
                    "Use /agents to see available agents.",
                    parse_mode="Markdown"
                )
                return

            agent_identifier = context.args[0]

            async with async_session_maker() as db:
                # Try to find by name first, then by UUID if it looks like one
                from uuid import UUID as PyUUID
                try:
                    agent_uuid = PyUUID(agent_identifier)
                    result = await db.execute(
                        select(Agent).where(
                            (Agent.name == agent_identifier) |
                            (Agent.id == agent_uuid)
                        )
                    )
                except ValueError:
                    # Not a valid UUID, search by name only
                    result = await db.execute(
                        select(Agent).where(Agent.name == agent_identifier)
                    )
                agent = result.scalar_one_or_none()

                if not agent:
                    await update.message.reply_text(f"❌ Agent '{agent_identifier}' not found")
                    return

                # Update strategy config to enable dry_run
                # Create a new dict to ensure SQLAlchemy detects the change
                config = dict(agent.strategy_config or {})
                config["dry_run"] = True
                agent.strategy_config = config
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(agent, "strategy_config")
                await db.commit()

                message = (
                    f"🟢 *DRY-RUN MODE ENABLED*\n\n"
                    f"🤖 Agent: {agent.name}\n"
                    f"🧪 Mode: *DRY-RUN* (simulated trades)\n\n"
                    f"✅ Agent will log opportunities but NOT execute real trades.\n\n"
                    f"🔄 Restart agent with `/stop_agent` then `/start_agent` to apply."
                )
                await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Go dry error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def agent_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /agent_config command - View agent configuration."""
        user_id = update.effective_user.id

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        try:
            if not context.args or len(context.args) < 1:
                await update.message.reply_text(
                    "❌ Usage: `/agent_config <agent_name>`\n\n"
                    "Use /agents to see available agents.",
                    parse_mode="Markdown"
                )
                return

            agent_identifier = context.args[0]

            async with async_session_maker() as db:
                # Try to find by name first, then by UUID if it looks like one
                from uuid import UUID as PyUUID
                try:
                    agent_uuid = PyUUID(agent_identifier)
                    result = await db.execute(
                        select(Agent).where(
                            (Agent.name == agent_identifier) |
                            (Agent.id == agent_uuid)
                        )
                    )
                except ValueError:
                    # Not a valid UUID, search by name only
                    result = await db.execute(
                        select(Agent).where(Agent.name == agent_identifier)
                    )
                agent = result.scalar_one_or_none()

                if not agent:
                    await update.message.reply_text(f"❌ Agent '{agent_identifier}' not found")
                    return

                config = agent.strategy_config or {}
                dry_run = config.get("dry_run", True)
                mode_emoji = "🧪" if dry_run else "🔴"
                mode_text = "DRY-RUN" if dry_run else "LIVE"

                message = (
                    f"⚙️ *Agent Configuration*\n\n"
                    f"🤖 *Agent:* {agent.name}\n"
                    f"📊 *Strategy:* {agent.strategy_type}\n"
                    f"{mode_emoji} *Mode:* {mode_text}\n"
                    f"📈 *Status:* {agent.status}\n\n"
                    f"*Strategy Settings:*\n"
                    f"```\n"
                )

                for key, value in config.items():
                    message += f"  {key}: {value}\n"

                message += (
                    f"```\n\n"
                    f"💡 *Commands:*\n"
                    f"  `/go_live {agent.name}` - Enable real trading\n"
                    f"  `/go_dry {agent.name}` - Enable dry-run mode"
                )

                await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Agent config error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)[:100]}")

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

                # Generate QR code for address
                qr_buffer = self.generate_deposit_qr(account.address)

                caption = (
                    f"💰 *Deposit Information*\n\n"
                    f"🏦 *Wallet Address:*\n`{account.address}`\n\n"
                    f"📝 *Instructions:*\n"
                    f"  • Send USDC (Polygon) to the address above\n"
                    f"  • Minimum deposit: 10 USDC\n"
                    f"  • Use Polygon network (not Ethereum)\n"
                    f"  • Transaction will appear after confirmation\n\n"
                    f"🔄 Use /sync to check for deposits after sending"
                )

                await update.message.reply_photo(
                    photo=InputFile(qr_buffer, filename="deposit_qr.png"),
                    caption=caption,
                    parse_mode="Markdown"
                )

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

    # ============== AI Chat Commands ==============

    async def ai_chat_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all non-command messages with AI chat."""
        user_id = update.effective_user.id
        chat_type = update.effective_chat.type
        chat_id = update.effective_chat.id

        logger.info(f"[AI Chat] Received message from user {user_id} in {chat_type}")

        if not await self.is_authorized(user_id):
            logger.warning(f"[AI Chat] User {user_id} not authorized")
            return

        if not config.ai.chat_enabled:
            logger.warning("[AI Chat] Feature disabled in config")
            # Only notify in private chat
            if chat_type == "private":
                await update.message.reply_text("AI chat feature is currently disabled.")
            return

        user_message = update.message.text

        if not user_message or len(user_message.strip()) == 0:
            logger.warning("[AI Chat] Empty message received")
            return

        # Handle group chats differently
        if chat_type in ("group", "supergroup"):
            await self._handle_group_chat(update, context, user_id, chat_id, user_message)
        else:
            # Private chat - always respond
            await self._handle_private_chat(update, context, user_id, user_message)

    async def _handle_group_chat(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        chat_id: int,
        user_message: str
    ):
        """Handle messages in group chats with smart filtering."""
        try:
            # Get bot username
            bot_user = await self.application.bot.get_me()
            bot_username = bot_user.username or "void_bot"

            # Check if this is a reply to the bot's message
            is_reply_to_bot = False
            if update.message.reply_to_message:
                reply_from = update.message.reply_to_message.from_user
                if reply_from and reply_from.id == bot_user.id:
                    is_reply_to_bot = True

            # Get recent chat context from context.chat_data
            chat_context = context.chat_data.get("recent_messages", "")

            # Store this message in context for future reference
            username = update.effective_user.username or update.effective_user.first_name or "anon"
            new_context = f"@{username}: {user_message}\n"
            context.chat_data["recent_messages"] = (chat_context + new_context)[-2000:]  # Keep last 2000 chars

            async with async_session_maker() as db:
                chat_service = ChatService(db)

                # Check if bot should respond
                should_respond, reason = await chat_service.should_respond_in_group(
                    message=user_message,
                    bot_username=bot_username,
                    is_reply_to_bot=is_reply_to_bot,
                    chat_context=chat_context,
                )

                logger.info(
                    f"[Group Chat] should_respond={should_respond}, reason={reason}, "
                    f"message={user_message[:50]}..."
                )

                if not should_respond:
                    return  # Silently ignore

                # Send typing action
                await update.message.chat.send_action("typing")

                # Get AI response using group chat mode
                response = await chat_service.group_chat(
                    user_id=user_id,
                    username=username,
                    message=user_message,
                    chat_id=chat_id,
                    chat_context=chat_context,
                )

                # Truncate if needed
                if len(response) > 4000:
                    response = response[:3997] + "..."

                # Reply to the message
                await update.message.reply_text(response)

                # Store bot response in context
                context.chat_data["recent_messages"] = (
                    context.chat_data.get("recent_messages", "") + f"VOID: {response}\n"
                )[-2000:]

        except Exception as e:
            logger.error(f"[Group Chat] Error: {e}", exc_info=True)
            # Don't spam error messages in group

    async def _handle_private_chat(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        user_message: str
    ):
        """Handle messages in private chats."""
        logger.info(f"[AI Chat] Processing private message: {user_message[:50]}...")

        try:
            async with async_session_maker() as db:
                chat_service = ChatService(db)

                # Send typing action
                await update.message.chat.send_action("typing")

                # Check for URLs in message - fetch and include content
                import re
                urls = re.findall(r'https?://[^\s]+', user_message)
                url_context = ""
                if urls:
                    for url in urls[:2]:  # Max 2 URLs
                        content = await chat_service.fetch_url_content(url)
                        if content:
                            url_context += f"\n[Content from {url[:50]}]: {content}\n"

                # Append URL context to message if found
                full_message = user_message
                if url_context:
                    full_message = f"{user_message}\n\n---\nURL Contents:{url_context}"

                # Get AI response
                response = await chat_service.chat(user_id, full_message)

                logger.info(f"[AI Chat] Got response: {response[:100]}...")

                # Truncate if needed
                if len(response) > 4000:
                    response = response[:3997] + "..."

                await update.message.reply_text(response)
                logger.info("[AI Chat] Response sent successfully")

        except Exception as e:
            logger.error(f"[AI Chat] Error: {e}", exc_info=True)
            await update.message.reply_text(
                f"something went wrong, try again in a sec"
            )

    async def ask_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ask command - explicit AI question."""
        user_id = update.effective_user.id

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        if not config.ai.chat_enabled:
            await update.message.reply_text("⚠️ AI chat feature is currently disabled.")
            return

        # Get question from arguments
        if not context.args or len(context.args) == 0:
            await update.message.reply_text(
                "❓ *Usage:* /ask <your question>\n\n"
                "Example: /ask What's my current portfolio status?",
                parse_mode="Markdown"
            )
            return

        question = " ".join(context.args)

        try:
            async with async_session_maker() as db:
                chat_service = ChatService(db)

                await update.message.chat.send_action("typing")

                response = await chat_service.chat(user_id, question)

                if len(response) > 4000:
                    response = response[:4000-3] + "..."

                # Send as plain text to avoid Markdown parsing errors
                await update.message.reply_text(response)

        except Exception as e:
            logger.error(f"Ask command error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def research_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /research command - research a specific market."""
        user_id = update.effective_user.id

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        # Get market ID from arguments
        if not context.args or len(context.args) == 0:
            await update.message.reply_text(
                "🔬 *Usage:* /research <market_id>\n\n"
                "Example: /research 0x1234abcd...\n\n"
                "Researches the market and provides AI analysis.",
                parse_mode="Markdown"
            )
            return

        market_id = context.args[0]

        try:
            async with async_session_maker() as db:
                # Check if market exists
                market = await db.get(Market, market_id)
                if not market:
                    await update.message.reply_text(
                        f"❌ Market `{market_id[:10]}...` not found in database.",
                        parse_mode="Markdown"
                    )
                    return

                await update.message.chat.send_action("typing")

                # Research market
                knowledge_service = KnowledgeService(db)
                results = await knowledge_service.research_market(market_id, force=True)

                # Get AI summary
                chat_service = ChatService(db)
                summary = await chat_service.research_market(market_id, user_id)

                response = (
                    f"🔬 Market Research Complete\n\n"
                    f"Market: {market.question[:80]}...\n\n"
                    f"📊 Results:\n"
                    f"• Tweets collected: {results.get('tweets_collected', 0)}\n"
                    f"• Sentiment: {results.get('sentiment', {}).get('avg_score', 'N/A')}\n"
                    f"• Knowledge entries: {results.get('knowledge_created', 0)}\n\n"
                    f"📝 AI Analysis:\n{summary}\n\n"
                    f"⏰ Researched at: {results.get('started_at', 'N/A')}"
                )

                if len(response) > 4000:
                    response = response[:4000-3] + "..."

                # Send as plain text to avoid Markdown parsing errors
                await update.message.reply_text(response)

        except Exception as e:
            logger.error(f"Research command error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def trends_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /trends command - show Twitter trends."""
        user_id = update.effective_user.id

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        try:
            async with async_session_maker() as db:
                from void.data.feeds.twitter_client import TwitterClient

                twitter_client = TwitterClient()
                await update.message.chat.send_action("typing")

                # Get trends
                trends = await twitter_client.get_trends()

                if not trends:
                    await update.message.reply_text(
                        "📊 No trending topics available right now."
                    )
                    return

                # Format trends
                trend_lines = [f"🔹 {trend}" for trend in trends[:10]]

                response = (
                    "📊 *Twitter Trends*\n\n"
                    + "\n".join(trend_lines) +
                    "\n\n💡 *Tip:* Use /ask to learn more about any trend."
                )

                await update.message.reply_text(response, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Trends command error: {e}", exc_info=True)
            await update.message.reply_text(
                f"⚠️ Could not fetch trends: {str(e)[:100]}"
            )

    async def news_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /news command - show latest news for markets."""
        user_id = update.effective_user.id

        if not await self.is_authorized(user_id):
            await update.message.reply_text("⛔ Not authorized")
            return

        try:
            async with async_session_maker() as db:
                from void.data.models import MarketKnowledge
                from sqlalchemy import select

                await update.message.chat.send_action("typing")

                # Get recent knowledge entries (news type)
                result = await db.execute(
                    select(MarketKnowledge)
                    .where(MarketKnowledge.content_type == "news")
                    .order_by(MarketKnowledge.collected_at.desc())
                    .limit(10)
                )
                news_items = result.scalars().all()

                if not news_items:
                    await update.message.reply_text(
                        "📰 No recent news available. "
                        "Use /research to collect news for markets."
                    )
                    return

                # Format news
                news_lines = []
                for item in news_items[:5]:
                    title = item.title or item.summary[:80] if item.summary else "No title"
                    news_lines.append(
                        f"📰 *{title[:60]}...*\n"
                        f"   Market: `{item.market_id[:10]}...`\n"
                        f"   Time: {item.collected_at.strftime('%H:%M')}\n"
                    )

                response = (
                    "📰 *Latest Market News*\n\n" +
                    "\n".join(news_lines) +
                    f"\n💡 Total news entries: {len(news_items)}"
                )

                await update.message.reply_text(response, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"News command error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)[:100]}")

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

        # AI Chat commands
        self.application.add_handler(CommandHandler("ask", self.ask_command))
        self.application.add_handler(CommandHandler("research", self.research_command))
        self.application.add_handler(CommandHandler("trends", self.trends_command))
        self.application.add_handler(CommandHandler("news", self.news_command))

        # Admin commands
        self.application.add_handler(CommandHandler("start_agent", self.start_agent))
        self.application.add_handler(CommandHandler("stop_agent", self.stop_agent))
        self.application.add_handler(CommandHandler("delete_agent", self.delete_agent))
        self.application.add_handler(CommandHandler("go_live", self.go_live))
        self.application.add_handler(CommandHandler("go_dry", self.go_dry))
        self.application.add_handler(CommandHandler("agent_config", self.agent_config))
        self.application.add_handler(CommandHandler("close_position", self.close_position))
        self.application.add_handler(CommandHandler("deposit", self.deposit))
        self.application.add_handler(CommandHandler("withdraw", self.withdraw))

        # AI Chat message handler (catch-all for non-command messages)
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.ai_chat_handler)
        )

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
                BotCommand("ask", "🤖 Ask AI anything"),
                BotCommand("research", "🔬 Research market"),
                BotCommand("trends", "📊 Twitter trends"),
                BotCommand("news", "📰 Market news"),
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

        # Start background task scheduler
        logger.info("🔄 Starting background task scheduler...")
        await self.scheduler.start()

        # Auto-resume agents that were running before bot restart
        await self._resume_running_agents()

        logger.info("🤖 VOID Bot started polling")

    async def _resume_running_agents(self):
        """Resume agents that were marked as RUNNING in the database."""
        try:
            async with async_session_maker() as db:
                # Find all agents with RUNNING status
                result = await db.execute(
                    select(Agent).where(Agent.status == AgentStatus.RUNNING)
                )
                running_agents = result.scalars().all()

                if not running_agents:
                    logger.info("🤖 No agents to resume")
                    return

                logger.info(f"🤖 Found {len(running_agents)} agents to resume")

                for agent in running_agents:
                    try:
                        agent_id_str = str(agent.id)
                        if agent_id_str in self._running_agents:
                            continue  # Already running

                        # Create and start the agent scan loop
                        task = asyncio.create_task(
                            self._create_agent_scan_loop(agent.id, agent.name, agent.telegram_user_id)
                        )
                        self._running_agents[agent_id_str] = {
                            "task": task,
                            "name": agent.name,
                            "started_at": datetime.utcnow()
                        }
                        logger.info(f"🤖 Resumed agent: {agent.name}")
                    except Exception as e:
                        logger.error(f"Failed to resume agent {agent.name}: {e}")

        except Exception as e:
            logger.error(f"Error resuming agents: {e}")

    async def _create_agent_scan_loop(self, agent_id: int, agent_name: str, user_id: int):
        """
        Background task that runs the full oracle latency trading pipeline.

        Pipeline steps:
        1. Fetch markets from Polymarket Gamma API
        2. Convert to Market models
        3. Scan for oracle latency opportunities using strategy
        4. Verify signals with AI (Z.ai GLM-4.7)
        5. Execute trades (or log in dry-run mode)
        6. Persist signals and orders to database
        """
        agent_id_str = str(agent_id)
        try:
            logger.info(f"[Agent] Starting full trading pipeline for {agent_name}")

            while agent_id_str in self._running_agents:
                try:
                    async with async_session_maker() as db:
                        from void.data.feeds.polymarket import GammaClient
                        from void.strategies.oracle_latency import OracleLatencyStrategy, OracleLatencyConfig
                        from void.strategies.base import StrategyContext
                        from void.data.models import Signal, SignalStatus
                        from decimal import Decimal

                        # Get fresh agent data
                        result = await db.execute(
                            select(Agent).where(Agent.id == agent_id)
                        )
                        agent = result.scalar_one_or_none()

                        if not agent or agent.status != AgentStatus.RUNNING:
                            logger.info(f"[Agent] {agent_name} stopped or not found")
                            break

                        # Get agent config
                        strategy_config = agent.strategy_config or {}
                        dry_run = strategy_config.get("dry_run", True)  # Default to dry-run for safety

                        # Initialize strategy with config
                        config = OracleLatencyConfig(**strategy_config)
                        strategy = OracleLatencyStrategy(config)
                        await strategy.start()

                        # Fetch markets from Polymarket
                        gamma = GammaClient()
                        logger.info(f"[Agent] {agent_name} fetching markets from Polymarket...")

                        markets_data = await gamma.get_markets(
                            active=True,
                            closed=True,  # Include closed but not resolved markets
                            limit=100,
                            min_liquidity=float(config.min_liquidity_usd),
                        )

                        # Convert to Market models and build cache
                        markets = []
                        market_cache = {}
                        for market_data in markets_data:
                            try:
                                market = gamma.to_market_model(market_data)
                                markets.append(market)
                                market_cache[market.id] = market
                            except Exception as e:
                                logger.debug(f"[Agent] Failed to parse market: {e}")

                        logger.info(f"[Agent] {agent_name} parsed {len(markets)} markets")

                        # Build strategy context
                        context = StrategyContext(
                            agent_id=agent.id,
                            account_id=agent.account_id,
                            config=config,
                            active_positions=[],
                            pending_orders=[],
                            recent_signals=[],
                            market_cache=market_cache,
                        )

                        # Scan for signals
                        signals_detected = 0
                        signals_verified = 0
                        signals_executed = 0

                        async for signal in strategy.scan_markets(markets, context):
                            signals_detected += 1

                            # Persist signal to database
                            db.add(signal)
                            await db.flush()

                            logger.info(
                                f"[Agent] Signal detected: {signal.predicted_outcome} "
                                f"on market {signal.market_id[:20]}... @ ${float(signal.entry_price):.3f} "
                                f"(margin: {float(signal.profit_margin)*100:.1f}%)"
                            )

                            # Verify signal with AI
                            verified_signal = await strategy.verify_signal(signal, context)

                            if verified_signal.status == SignalStatus.VERIFIED:
                                signals_verified += 1

                                logger.info(
                                    f"[Agent] Signal VERIFIED with {float(verified_signal.confidence)*100:.0f}% confidence "
                                    f"(source: {verified_signal.verification_source})"
                                )

                                # Execute trade (or simulate in dry-run)
                                if dry_run:
                                    logger.info(
                                        f"[Agent] DRY-RUN: Would buy {verified_signal.predicted_outcome} "
                                        f"@ ${float(verified_signal.entry_price):.3f}"
                                    )
                                    verified_signal.status = SignalStatus.EXECUTED
                                    verified_signal.executed_at = datetime.utcnow()
                                    signals_executed += 1
                                else:
                                    # Generate and execute orders
                                    order_requests = await strategy.generate_orders(verified_signal, context)

                                    for order_request in order_requests:
                                        try:
                                            from void.execution.models import OrderRequest, OrderSide, OrderType
                                            from void.execution.engine import ExecutionEngine
                                            from void.accounts.service import AccountService

                                            # Create execution engine
                                            account_service = AccountService(db)
                                            execution_engine = ExecutionEngine(db, account_service)

                                            # Build order request
                                            exec_request = OrderRequest(
                                                market_id=order_request["market_id"],
                                                token_id=order_request["token_id"],
                                                side=OrderSide[order_request["side"].upper()],
                                                order_type=OrderType[order_request["order_type"]],
                                                price=Decimal(str(order_request["price"])),
                                                size=Decimal(str(order_request["size"])),
                                                signal_id=signal.id,
                                            )

                                            # Execute order
                                            result = await execution_engine.execute_order(
                                                exec_request,
                                                agent.account_id
                                            )

                                            if result.success:
                                                logger.info(
                                                    f"[Agent] ORDER EXECUTED: {result.clob_order_id} "
                                                    f"(latency: {result.latency_ms}ms)"
                                                )
                                                verified_signal.status = SignalStatus.EXECUTED
                                                verified_signal.executed_at = datetime.utcnow()
                                                signals_executed += 1
                                            else:
                                                logger.error(
                                                    f"[Agent] Order failed: {result.error}"
                                                )

                                        except Exception as e:
                                            logger.error(f"[Agent] Execution error: {e}")

                            else:
                                logger.info(
                                    f"[Agent] Signal rejected: {verified_signal.status.value} "
                                    f"(confidence: {float(verified_signal.confidence)*100:.0f}%)"
                                )

                            # Save signal updates
                            await db.commit()

                        # Update heartbeat
                        agent.last_heartbeat = datetime.utcnow()
                        await db.commit()

                        # Close gamma client session
                        await gamma.close()

                        logger.info(
                            f"[Agent] {agent_name} scan complete | "
                            f"Markets: {len(markets)} | "
                            f"Detected: {signals_detected} | "
                            f"Verified: {signals_verified} | "
                            f"Executed: {signals_executed}"
                        )

                    # Wait before next scan
                    scan_interval = strategy_config.get("scan_interval_seconds", 30)
                    await asyncio.sleep(scan_interval)

                except asyncio.CancelledError:
                    logger.info(f"[Agent] {agent_name} scan loop cancelled")
                    break
                except Exception as e:
                    logger.error(f"[Agent] {agent_name} scan error: {e}", exc_info=True)
                    await asyncio.sleep(60)  # Wait longer on error

        except Exception as e:
            logger.error(f"[Agent] {agent_name} loop crashed: {e}", exc_info=True)
        finally:
            # Clean up
            if agent_id_str in self._running_agents:
                del self._running_agents[agent_id_str]
            logger.info(f"[Agent] {agent_name} loop ended")

    async def stop(self):
        """Stop bot."""
        # Stop running agents
        for agent_id_str, agent_info in list(self._running_agents.items()):
            try:
                agent_info["task"].cancel()
                logger.info(f"Stopped agent: {agent_info['name']}")
            except Exception as e:
                logger.error(f"Error stopping agent: {e}")
        self._running_agents.clear()

        # Stop background scheduler first
        logger.info("🔄 Stopping background task scheduler...")
        await self.scheduler.stop()

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

        # Start background task scheduler
        logger.info("🔄 Starting background task scheduler...")
        await self.scheduler.start()

        logger.info(f"🤖 VOID Bot started with webhook: {webhook_url}")
