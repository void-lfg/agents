#!/usr/bin/env python3
"""
Test VOID Telegram Bot

This script tests basic bot connectivity without starting the full service.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from void.bot.config import TelegramBotConfig


async def test_bot_config():
    """Test bot configuration."""
    print("🔍 Testing VOID Telegram Bot Configuration")
    print("=" * 50)

    try:
        config = TelegramBotConfig()

        print(f"\n✅ Configuration loaded successfully!\n")
        print(f"📝 Bot Token: {config.token[:20]}...{config.token[-10:]}")
        print(f"🌐 Webhook URL: {config.webhook_url or 'Not set (polling mode)'}")
        print(f"👥 Allowed Users: {len(config.allowed_user_ids)} users")
        print(f"👑 Admin Users: {len(config.admin_user_ids)} admins")
        print(f"\n🔔 Notifications:")
        print(f"  • Signals: {config.notify_on_signal}")
        print(f"  • Trades: {config.notify_on_trade}")
        print(f"  • Errors: {config.notify_on_error}")

        print(f"\n✅ Bot is configured and ready!")
        print(f"\n🚀 To start the bot:")
        print(f"   python src/bot_runner.py")

        return True

    except Exception as e:
        print(f"\n❌ Error loading config: {e}")
        return False


async def test_bot_connection():
    """Test bot connection to Telegram."""
    from telegram import Bot

    print("\n" + "=" * 50)
    print("🔌 Testing Telegram Connection")
    print("=" * 50)

    try:
        config = TelegramBotConfig()
        bot = Bot(token=config.token)

        # Get bot info
        bot_info = await bot.get_me()

        print(f"\n✅ Connected to Telegram!\n")
        print(f"🤖 Bot Info:")
        print(f"  • Name: {bot_info.first_name}")
        print(f"  • Username: @{bot_info.username}")
        print(f"  • ID: {bot_info.id}")
        print(f"  • Can join groups: {bot_info.can_join_groups}")
        print(f"  • Can read all group messages: {bot_info.can_read_all_group_messages}")

        print(f"\n🎉 Bot is working! Send a message to @{bot_info.username} on Telegram!")

        return True

    except Exception as e:
        print(f"\n❌ Error connecting to Telegram: {e}")
        print(f"\n💡 Make sure the bot token is correct in .env")
        return False


async def main():
    """Run all tests."""
    # Test 1: Configuration
    config_ok = await test_bot_config()

    if not config_ok:
        print("\n❌ Configuration test failed. Please check your .env file.")
        sys.exit(1)

    # Test 2: Telegram Connection
    connection_ok = await test_bot_connection()

    if not connection_ok:
        print("\n❌ Connection test failed. Please check your bot token.")
        sys.exit(1)

    print("\n" + "=" * 50)
    print("✅ All tests passed! Bot is ready to use!")
    print("=" * 50)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Test interrupted")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
