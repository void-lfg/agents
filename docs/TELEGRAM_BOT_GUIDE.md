# 🤖 VOID Telegram Bot - Complete Guide

**Bot Username**: @void_lfg_bot
**Status**: ✅ Production Ready
**Version**: 1.0.0

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Setup](#setup)
4. [Commands](#commands)
5. [Notifications](#notifications)
6. [Security](#security)
7. [Troubleshooting](#troubleshooting)

---

## 🚀 Overview

The VOID Telegram Bot provides a convenient interface to monitor and control your VOID trading agent from anywhere. Get real-time notifications, check positions, start/stop agents, and more - all from Telegram!

### Why Use the Bot?

- 📱 **Mobile Access** - Monitor trades from anywhere
- 🔔 **Real-time Alerts** - Instant notifications on signals and trades
- 🎛️ **Remote Control** - Start/stop agents on the go
- 📊 **Quick Stats** - Check portfolio and positions instantly
- 🤖 **Easy to Use** - Simple command-based interface

---

## ✨ Features

### Monitoring
- ✅ System status checks
- ✅ Portfolio overview
- ✅ Open positions tracking
- ✅ Recent signals history
- ✅ Agent status monitoring

### Control
- ✅ Start/stop trading agents
- ✅ List all agents
- ✅ View agent details

### Notifications
- ✅ New signal alerts
- ✅ Trade execution notifications
- ✅ Error alerts
- ✅ Configurable notification types

### Security
- ✅ User authorization
- ✅ Admin-only commands
- ✅ Configurable access control

---

## ⚡ Quick Start

### 1. Start the Bot

```bash
# Option A: Run directly
python src/bot_runner.py

# Option B: Run with nohup (background)
nohup python src/bot_runner.py > bot.log 2>&1 &

# Option C: Run with systemd/supervisor (production)
# See Deployment section
```

### 2. Open Telegram

1. Search for `@void_lfg_bot`
2. Click **Start** or send `/start`
3. Bot will welcome you and show available commands

### 3. Try Commands

```
/status      - Check system status
/portfolio   - View your portfolio
/positions   - See open positions
/help        - Show all commands
```

---

## 📖 Commands Reference

### 🏠 Basic Commands

#### `/start`
**Description**: Start the bot and see welcome message

**Usage**:
```
/start
```

**Response**:
```
🤖 Welcome to VOID Trading Agent!

I'm your autonomous trading assistant for Polymarket
prediction markets.

Commands:
/status - Check system status
/portfolio - View your portfolio
/positions - See open positions
/signals - Recent trading signals
/agent - Control trading agent
/help - Show all commands

Let's make some money! 🚀💰
```

---

#### `/help`
**Description**: Show all available commands

**Usage**:
```
/help
```

**Response**:
```
📖 VOID Bot Commands

📊 Monitoring:
/status - System status and stats
/portfolio - Account balances and value
/positions - Open trading positions
/signals - Recent trading signals
/logs - Recent system logs

🤖 Agent Control:
/agent - Start/stop trading agent
/agents - List all agents

⚙️ Settings:
/settings - Configure notifications

❓ Help:
/help - Show this message
/about - About VOID
```

---

### 📊 Monitoring Commands

#### `/status`
**Description**: View system status and statistics

**Usage**:
```
/status
```

**Response**:
```
🔍 System Status

📊 Database:
  • Accounts: 1
  • Agents: 1
  • Signals: 25
  • Open Positions: 3

🤖 Active Agent:
  • Name: oracle-latency-agent-1
  • Strategy: ORACLE_LATENCY
  • Status: RUNNING
  • Heartbeat: 10:30:45

💰 Total P&L: $127.50
```

---

#### `/portfolio`
**Description**: View account balances

**Usage**:
```
/portfolio
```

**Response**:
```
💼 Portfolio Overview

🏦 demo-account
  • USDC: $1,250.00
  • MATIC: 12.3456
  • Address: 0x7f3a...9c2d
```

---

#### `/positions`
**Description**: View open trading positions

**Usage**:
```
/positions
```

**Response**:
```
📊 Open Positions (3)

🎯 Market: 0x1234...5678
  • Side: LONG
  • Size: $500.00
  • Entry: 0.8500
  • P&L: +$75.00
  • Entered: 01/02 14:30

🎯 Market: 0xabcd...ef01
  • Side: LONG
  • Size: $300.00
  • Entry: 0.7800
  • P&L: +$45.00
  • Entered: 01/02 15:45
```

---

#### `/signals`
**Description**: View recent trading signals

**Usage**:
```
/signals
```

**Response**:
```
📈 Recent Signals (25)

🎯 Signal: BUY_YES
  • Market: 0x1234...5678
  • Outcome: YES
  • Confidence: 98%
  • Profit: 17.6%
  • Status: EXECUTED
  • Time: 01/02 14:30
```

---

#### `/agents`
**Description**: List all trading agents

**Usage**:
```
/agents
```

**Response**:
```
🤖 Trading Agents (2)

🏃 oracle-latency-agent-1
  • Strategy: ORACLE_LATENCY
  • Status: RUNNING
  • Max Position: $500
  • Created: 01/01/2026

💤 oracle-latency-agent-2
  • Strategy: ORACLE_LATENCY
  • Status: IDLE
  • Max Position: $300
  • Created: 01/01/2026
```

---

### 🎛️ Control Commands

#### `/agent`
**Description**: Control trading agents (admin only)

**Usage**:
```
/agent
```

**Response**:
```
🎛️ Agent Control

Select an agent to control:
[⏹️ Stop oracle-latency-agent-1]
```

**Note**: Admin privileges required

---

#### `/about`
**Description**: About VOID

**Usage**:
```
/about
```

**Response**:
```
🤖 About VOID

VOID is an autonomous trading agent for Polymarket
prediction markets.

Version: 1.0.0
Strategy: Oracle Latency Arbitrage
AI Model: Z.ai GLM-4.7

🚀 Features:
• 24/7 automated trading
• AI-powered outcome verification
• Real-time market scanning
• Risk management
• Portfolio tracking

Built with ❤️ using Python and Telegram Bot API
```

---

## 🔔 Notifications

### Signal Notifications

Get notified instantly when the bot detects a trading opportunity!

**Example**:
```
🚨 New Signal Detected!

🎯 Market: 0x1234...5678
  • Type: BUY_YES
  • Outcome: YES
  • Confidence: 98%
  • Profit: 17.6%
  • Time: 14:30:45

Strategy: ORACLE_LATENCY
```

---

### Trade Notifications

Know when trades are executed!

**Example**:
```
💼 Trade Executed!

🎯 Market: 0x1234...5678
  • Side: LONG
  • Size: $500.00
  • Entry: 0.8500
  • Time: 14:31:02

Position ID: a3f8d2e1...
```

---

### Error Notifications

Get alerted on errors immediately!

**Example**:
```
⚠️ VOID Error

```
Connection failed to Polymarket API
Retrying in 30 seconds...
```

Time: 2026-01-02 14:25:00 UTC
```

---

## 🔒 Security

### Access Control

Configure who can use your bot:

**In `.env`:**
```bash
# Allow specific users (empty = all users allowed)
TELEGRAM_ALLOWED_USER_IDS=[123456789, 987654321]

# Admin users can control agents
TELEGRAM_ADMIN_USER_IDS=[123456789]
```

**How to get your Telegram User ID:**
1. Message `@userinfobot` on Telegram
2. It will reply with your User ID
3. Add the ID to `.env`

---

### Best Practices

1. **Set Admin IDs** - Only you should control agents
2. **Use Webhooks** - For production, use webhooks instead of polling
3. **Monitor Logs** - Check bot logs regularly
4. **Secure Token** - Never share your bot token
5. **Limit Access** - Use ALLOWED_USER_IDS in production

---

## 🚢 Deployment

### Development (Polling)

```bash
python src/bot_runner.py
```

---

### Production (Webhook)

**1. Set up webhook URL:**
```bash
# In .env
TELEGRAM_WEBHOOK_URL=https://your-domain.com/webhook/telegram
```

**2. Run bot:**
```bash
python src/bot_runner.py
```

**3. Configure reverse proxy:**
```nginx
location /webhook/telegram {
    proxy_pass http://localhost:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

---

### Systemd Service

**Create `/etc/systemd/system/void-bot.service`:**
```ini
[Unit]
Description=VOID Telegram Bot
After=network.target

[Service]
Type=simple
User=void
WorkingDirectory=/home/void/void
Environment="PATH=/home/void/void/venv/bin"
ExecStart=/home/void/void/venv/bin/python src/bot_runner.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Start service:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable void-bot
sudo systemctl start void-bot
sudo systemctl status void-bot
```

---

## 🐛 Troubleshooting

### Bot Not Responding

**Problem**: Commands don't work

**Solution**:
```bash
# Check if bot is running
ps aux | grep bot_runner

# Check logs
tail -f bot.log

# Restart bot
pkill -f bot_runner
python src/bot_runner.py
```

---

### "Not Authorized" Error

**Problem**: Bot says you're not authorized

**Solution**:
1. Get your Telegram User ID from `@userinfobot`
2. Add to `.env`: `TELEGRAM_ALLOWED_USER_IDS=[YOUR_ID]`
3. Restart bot

---

### Webhook Not Working

**Problem**: Webhook not receiving updates

**Solution**:
```bash
# Check webhook URL
curl https://your-domain.com/webhook/telegram

# Check nginx logs
tail -f /var/log/nginx/error.log

# Delete webhook to fall back to polling
# In bot code, call:
# await bot.delete_webhook()
```

---

### Database Connection Failed

**Problem**: Bot can't connect to database

**Solution**:
```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Check DB credentials in .env
grep DB_ .env

# Test connection
psql -U void -d void -c "SELECT 1;"
```

---

## 🎯 Tips & Tricks

### 1. Create Bot Shortcuts

Add bot commands to Telegram's chat bar for quick access:

**Settings > Chat Settings > Quick Actions > Add Shortcuts**

### 2. Pin Important Messages

Pin the `/status` message for quick access to portfolio value

### 3. Use Bot in Groups

Add bot to groups (with admin permissions) for team monitoring

### 4. Schedule Reports

Use external tools to periodically request `/status` and log results

### 5. Integrate with Alerts

Use Telegram's built-in notifications to never miss a trade

---

## 📚 Additional Resources

- **Telegram Bot API**: https://core.telegram.org/bots/api
- **python-telegram-bot Docs**: https://docs.python-telegram-bot.org/
- **VOID Main Docs**: [README.md](../README.md)
- **CLI Guide**: [CLI_GUIDE.md](./CLI_GUIDE.md)

---

## 🆘 Support

### Test Bot Connection

```bash
python src/test_bot.py
```

### Check Logs

```bash
tail -f bot.log
```

### Verify Configuration

```bash
grep TELEGRAM_ .env
```

---

## 🎉 You're Ready!

**Your VOID Telegram Bot is ready to use!**

1. ✅ Bot is configured and tested
2. ✅ All commands implemented
3. ✅ Notifications working
4. ✅ Security features enabled

**Next Steps**:
1. Start the bot: `python src/bot_runner.py`
2. Open Telegram and message `@void_lfg_bot`
3. Try `/start` to begin
4. Check `/status` to see your system
5. Set up notifications to never miss a trade

---

**Happy Trading! 🚀💰🎯**

**Bot**: @void_lfg_bot
**Version**: 1.0.0
**Date**: January 2, 2026
