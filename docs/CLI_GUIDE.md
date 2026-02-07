# 🖥️ VOID Admin CLI - Complete Guide

**Version**: 1.0.0
**Status**: ✅ Production Ready

---

## 📋 Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [Command Reference](#command-reference)
4. [Examples](#examples)
5. [Troubleshooting](#troubleshooting)

---

## 🚀 Installation

### Option 1: Using the Setup Script (Recommended)

```bash
# Install VOID in editable mode
python3 -m venv venv
source venv/bin/activate
pip install -e .

# CLI is now available as 'void-admin'
void-admin --help
```

### Option 2: Direct Python Execution

```bash
# Run CLI directly without installing
python3 -m pip install click tabulate rich
python3 src/void/admin/cli/main.py --help
```

---

## ⚡ Quick Start

### 1. Test CLI Installation

```bash
void-admin --version
# Output: VOID Admin CLI version 1.0.0

void-admin --help
# Shows all available commands
```

### 2. Check System Status

```bash
void-admin status
```

**Output:**
```
🔍 VOID Trading Agent Status
==================================================

📊 Database:
  Accounts: 1
  Agents: 1
  Signals Detected: 15
  Open Positions: 3

🤖 Active Agent:
  Name: oracle-latency-agent-1
  Strategy: ORACLE_LATENCY
  Status: RUNNING
  Last Heartbeat: 2026-01-02 10:30:45

🔧 Environment: development
📝 Debug Mode: True
```

### 3. List Accounts

```bash
void-admin account list
```

**Output:**
```
┌────────────┬─────────────────┬──────────────┬────────┬────────┬────────────────────┐
│ ID         │ Name            │ Address      │ USDC   │ MATIC  │ Created            │
├────────────┼─────────────────┼──────────────┼────────┼────────┼────────────────────┤
│ a3f8d2e1... │ demo-account    │ 0x7f3a...9c2 │ $500.00│ 12.345 │ 2026-01-01 12:00   │
└────────────┴─────────────────┴──────────────┴────────┴────────┴────────────────────┘
```

### 4. List Agents

```bash
void-admin agent list
```

**Output:**
```
┌────┬────────────────────────┬─────────────────┬─────────┬────────────┬──────────┬────────┐
│    │ Name                   │ Strategy        │ Status  │ Account    │ Max Pos  │ Created│
├────┼────────────────────────┼─────────────────┼─────────┼────────────┼──────────┼────────┤
│ 🏃 │ oracle-latency-agent-1 │ ORACLE_LATENCY  │ RUNNING │ a3f8d2e1...│   500    │ 2026-01│
└────┴────────────────────────┴─────────────────┴─────────┴────────────┴──────────┴────────┘
```

---

## 📖 Command Reference

### Global Options

| Option | Short | Description |
|--------|-------|-------------|
| `--version` | | Show version and exit |
| `--verbose` | `-v` | Enable verbose output |
| `--config-file PATH` | | Use custom config file |
| `--help` | `-h` | Show help message |

---

### 🖥️ Status Commands

#### `void-admin status`

Show system status and statistics.

**Usage:**
```bash
void-admin status
```

**What it shows:**
- Number of accounts, agents, signals, positions
- Active agent details
- Environment configuration
- Database status

---

### 👤 Account Management

#### `void-admin account list`

List all trading accounts.

**Usage:**
```bash
void-admin account list
void-admin account list --format json  # JSON output
```

**Output Fields:**
- ID: Unique account identifier
- Name: Account name
- Address: Polygon wallet address
- USDC: USDC balance
- MATIC: MATIC balance
- Created: Creation timestamp

---

#### `void-admin account create`

Create a new trading account.

**Usage:**
```bash
# Interactive (prompts for name)
void-admin account create

# With specific name
void-admin account create --name "my-trading-account"

# With existing private key
void-admin account create --name "import-account" --private-key "0x..."
```

**What happens:**
1. Creates new wallet (if no private key provided)
2. Encrypts private key with AES-256-GCM
3. Stores in database
4. Shows wallet address

**⚠️ Important:**
- If wallet is generated, **BACKUP YOUR DATABASE**
- Private keys are encrypted but not recoverable if database is lost

---

#### `void-admin account sync`

Sync balances from blockchain.

**Usage:**
```bash
# Sync specific account
void-admin account sync <account_id>

# Sync all accounts
void-admin account sync --all
```

**What it does:**
- Queries Polygon blockchain
- Updates USDC and MATIC balances
- Saves to database

---

### 🤖 Agent Management

#### `void-admin agent list`

List all trading agents.

**Usage:**
```bash
void-admin agent list
void-admin agent list --format json
```

**Status Emojis:**
- 🏃 RUNNING - Agent is actively scanning markets
- 💤 IDLE - Agent is stopped
- ⏹️ STOPPED - Agent was manually stopped
- ❌ ERROR - Agent encountered an error

---

#### `void-admin agent start`

Start a trading agent.

**Usage:**
```bash
void-admin agent start <agent_id>
```

**What happens:**
1. Initializes strategy (Oracle Latency)
2. Connects to Polymarket APIs
3. Starts market scanning loop
4. Begins detecting trading opportunities
5. Executes trades when signals found

**Example:**
```bash
# Get agent ID first
void-admin agent list

# Start the agent
void-admin agent start a3f8d2e1-1234-5678-90ab-cdef12345678
```

---

#### `void-admin agent stop`

Stop a running agent.

**Usage:**
```bash
void-admin agent stop <agent_id>
```

**What happens:**
- Stops market scanning
- Cancels pending orders
- Updates agent status to STOPPED
- Closes connections

---

### 📊 Market Commands

#### `void-admin market list`

List Polymarket markets.

**Usage:**
```bash
# Show top 20 markets
void-admin market list

# Show 50 markets
void-admin market list --limit 50

# Filter by category
void-admin market list --category "Politics"

# Show only active markets
void-admin market list --active-only
```

**Output Fields:**
- Question: Market question
- Category: Market category (Politics, Sports, Crypto, etc.)
- Volume: 24h trading volume
- YES/NO: Current prices
- Status: Market status (ACTIVE, CLOSED, etc.)

---

### 💼 Position Commands

#### `void-admin position list`

List trading positions.

**Usage:**
```bash
# Show all positions
void-admin position list

# Show only open positions
void-admin position list --open-only

# Filter by account
void-admin position list --account-id <account_id>
```

**Output Fields:**
- ID: Position identifier
- Market: Market ID
- Side: LONG (YES) or SHORT (NO)
- Size: Position size in USD
- Entry: Entry price
- Status: OPEN, CLOSED, ERROR
- P&L: Profit or loss
- Entered: Entry timestamp

---

### 📈 Signal Commands

#### `void-admin signal list`

List trading signals.

**Usage:**
```bash
# Show recent signals
void-admin signal list

# Show more signals
void-admin signal list --limit 50

# Filter by strategy
void-admin signal list --strategy ORACLE_LATENCY
```

**Output Fields:**
- ID: Signal identifier
- Market: Market ID
- Strategy: Strategy that detected signal
- Type: Signal type (BUY_YES, BUY_NO)
- Outcome: Predicted outcome
- Confidence: AI confidence (if verified)
- Profit: Expected profit margin
- Status: Signal status
- Detected: Detection timestamp

---

### 📋 Logs Commands

#### `void-admin logs`

View agent logs.

**Usage:**
```bash
# Show last 50 lines
void-admin logs

# Show last 100 lines
void-admin logs --lines 100

# Follow logs (live tail)
void-admin logs --follow
# Press Ctrl+C to stop

# Aliases
void-admin logs -f     # Follow
void-admin logs -n 100 # Show 100 lines
```

**Log Format:**
```json
{
  "event": "signal_detected",
  "market_id": "0x1234...",
  "confidence": 0.98,
  "profit_margin": 0.176,
  "timestamp": "2026-01-02T10:30:45Z"
}
```

---

### 🧪 Test Commands

#### `void-admin test-api`

Test Polymarket API connection.

**Usage:**
```bash
void-admin test-api
```

**What it tests:**
1. Gamma API (Market Discovery)
2. CLOB API (Trading)
3. API credentials
4. Network connectivity

**Output:**
```
🔌 Testing Polymarket API Connection
==================================================

1. Testing Gamma API (Market Discovery)...
   ✅ Gamma API working - Found 1500 markets

2. Testing CLOB API (Trading)...
   ✅ CLOB API initialized
   📝 CLOB URL: https://clob.polymarket.com

==================================================
✅ API test complete
```

---

## 💡 Examples

### Example 1: Start Trading from Scratch

```bash
# 1. Check status
void-admin status

# 2. Create account
void-admin account create --name "my-trading-account"

# 3. List agents
void-admin agent list

# 4. Start agent
void-admin agent start <agent_id>

# 5. Monitor logs
void-admin logs --follow
```

### Example 2: Monitor Performance

```bash
# Check open positions
void-admin position list --open-only

# View recent signals
void-admin signal list --limit 20

# Check account balance
void-admin account list

# Follow live logs
void-admin logs --follow
```

### Example 3: Debug Issues

```bash
# Test API connection
void-admin test-api

# Check agent status
void-admin agent list

# View recent logs
void-admin logs --lines 100

# Check system status
void-admin status
```

### Example 4: Stop Trading

```bash
# Get agent ID
void-admin agent list

# Stop agent
void-admin agent stop <agent_id>

# Verify stopped
void-admin agent list

# Check final positions
void-admin position list
```

---

## 🛠️ Troubleshooting

### Issue: "Database connection failed"

**Solution:**
```bash
# Start PostgreSQL
docker-compose up -d postgres

# Or check if PostgreSQL is running
docker-compose ps

# Run migrations
alembic upgrade head
```

---

### Issue: "No agents found"

**Solution:**
```bash
# Agents are created automatically by main.py
# Run the main agent script
python src/main.py

# Or create manually via database
# (See documentation for manual agent creation)
```

---

### Issue: "API test failed"

**Solution:**
```bash
# Check .env file has correct credentials
grep POLYMARKET .env

# Verify API keys are valid
# Test with curl:
curl https://clob.polymarket.com/health
```

---

### Issue: "Module not found: void"

**Solution:**
```bash
# Install VOID in editable mode
pip install -e .

# Or add to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
```

---

### Issue: "Permission denied: void-admin"

**Solution:**
```bash
# Make script executable
chmod +x void-admin

# Or use python directly
python src/void/admin/cli/main.py <command>
```

---

## 🎯 Tips & Best Practices

### 1. Use Shell Aliases

```bash
# Add to ~/.bashrc or ~/.zshrc
alias va='void-admin'
alias va-status='void-admin status'
alias va-logs='void-admin logs -f'
alias va-positions='void-admin position list --open-only'
alias va-agents='void-admin agent list'
```

### 2. Monitor Continuously

```bash
# Watch positions update
watch -n 5 'void-admin position list --open-only'

# Follow logs in one terminal
void-admin logs --follow

# Check status in another
watch -n 10 'void-admin status'
```

### 3. Backup Regularly

```bash
# Export database
docker exec void-postgres pg_dump -U void void > backup.sql

# Export accounts
void-admin account list --format json > accounts-backup.json
```

### 4. JSON Output for Scripting

```bash
# Get accounts as JSON
void-admin account list --format json | jq '.[] | .name'

# Count total positions
void-admin position list --format json | jq 'length'

# Find most profitable signal
void-admin signal list --format json | jq 'max_by(.profit_margin)'
```

---

## 📚 Additional Resources

- **[Main README](../README.md)** - Project overview
- **[GETTING_STARTED](../.claude/GETTING_STARTED.md)** - Setup guide
- **[API Documentation](./API_GUIDE.md)** - Admin REST API (coming soon)

---

## 🆘 Support

If you encounter issues:

1. Check logs: `void-admin logs -n 100`
2. Test APIs: `void-admin test-api`
3. Check status: `void-admin status`
4. Review this guide's troubleshooting section

---

**Status**: ✅ **CLI READY TO USE**

**Built with Click, Tabulate, and Rich**
**Version**: 1.0.0
**Date**: January 2, 2026
