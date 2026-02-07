# 🚀 VOID Admin CLI - Quick Reference

**Cheat Sheet for Common Commands**

---

## 📋 Essential Commands

```bash
# Get help
void-admin --help
void-admin <command> --help

# Check system status
void-admin status

# Test API connection
void-admin test-api

# View logs
void-admin logs -f           # Follow logs
void-admin logs -n 100       # Last 100 lines
```

---

## 👤 Account Management

```bash
# List accounts
void-admin account list

# Create new account
void-admin account create --name "my-account"

# Sync balances from blockchain
void-admin account sync <account_id>
void-admin account sync --all
```

---

## 🤖 Agent Management

```bash
# List agents
void-admin agent list

# Start agent
void-admin agent start <agent_id>

# Stop agent
void-admin agent stop <agent_id>
```

---

## 📊 Viewing Data

```bash
# List markets
void-admin market list
void-admin market list --limit 50 --category "Politics"

# List positions
void-admin position list
void-admin position list --open-only

# List signals
void-admin signal list
void-admin signal list --limit 50
```

---

## 🔧 Common Workflows

### Start Trading
```bash
void-admin status                    # Check status
void-admin account list              # View accounts
void-admin agent list                # View agents
void-admin agent start <agent_id>    # Start agent
void-admin logs -f                   # Monitor logs
```

### Check Performance
```bash
void-admin position list --open-only # Open positions
void-admin signal list --limit 20    # Recent signals
void-admin account list              # Account balances
```

### Troubleshoot
```bash
void-admin test-api                  # Test APIs
void-admin logs -n 100              # Recent logs
void-admin status                    # System status
```

---

## 🎯 Output Formats

```bash
# Table format (default)
void-admin account list

# JSON format (for scripting)
void-admin account list --format json
```

---

## 💡 Pro Tips

1. **Create shell aliases**:
   ```bash
   alias va='void-admin'
   alias va-logs='void-admin logs -f'
   ```

2. **Watch positions continuously**:
   ```bash
   watch -n 5 'void-admin position list --open-only'
   ```

3. **Export to JSON for analysis**:
   ```bash
   void-admin signal list --format json | jq '.'
   ```

---

**Full Guide**: [CLI_GUIDE.md](./CLI_GUIDE.md)
