"""
VOID Telegram Bot - Runner script

Usage:
    python src/bot_runner.py              # Start bot (polling)
    python src/bot_runner.py --webhook    # Start bot (webhook)
"""

import asyncio
import sys
import signal
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from void.bot.config import TelegramBotConfig
from void.bot.bot import VoidBot
from void.config import config as void_config

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)

logger = structlog.get_logger()


async def main():
    """Main bot runner."""
    logger.info("void_bot_starting", version="1.0.0")

    # Load bot config
    bot_config = TelegramBotConfig()

    if not bot_config.token:
        logger.error("telegram_token_missing")
        print("❌ TELEGRAM_TOKEN not set in environment")
        sys.exit(1)

    # Create bot
    bot = VoidBot(bot_config)

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()

    def signal_handler(sig, frame):
        logger.info("shutdown_signal_received", signal=sig)
        asyncio.create_task(shutdown(bot))

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler, sig, None)

    # Start bot
    try:
        if bot_config.webhook_url:
            logger.info("starting_webhook_mode", webhook_url=bot_config.webhook_url)
            await bot.run_webhook(bot_config.webhook_url)

            # Keep running
            while True:
                await asyncio.sleep(3600)
        else:
            logger.info("starting_polling_mode")
            await bot.start_polling()

            # Keep running
            while True:
                await asyncio.sleep(3600)

    except Exception as e:
        logger.error("bot_error", error=str(e), exc_info=True)
        raise
    finally:
        await bot.stop()


async def shutdown(bot: VoidBot):
    """Graceful shutdown."""
    logger.info("shutting_down_bot")
    try:
        await bot.stop()
    except Exception as e:
        logger.error("shutdown_error", error=str(e))
    sys.exit(0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("bot_interrupted")
        sys.exit(0)
    except Exception as e:
        logger.error("bot_fatal_error", error=str(e), exc_info=True)
        sys.exit(1)
