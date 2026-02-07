# VOID Trading Agent - Quick Start Guide

## 🚀 Setup Instructions (5 minutes)

### 1. Install Dependencies

```bash
# Clone the repository
cd /path/to/void

# Run setup script
./scripts/setup.sh

# Or manually:
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 2. Configure Environment

The `.env` file is already configured with your Polymarket credentials:

```bash
# .env file already has:
POLYMARKET_API_KEY=019b77fa-c94c-73db-879c-200758955eb2
POLYMARKET_API_SECRET=DKW3twPvQp8UHE8XN5PjXPUXxRmu3b5-xBH1yixI2Ik=
POLYMARKET_API_PASSPHRASE=3e34b49085db294e3670df1e02872d8922dfd66369040cfd3331fc7459cc9ff6
```

You still need to add:
- `AI_OPENAI_API_KEY` - Get from https://platform.openai.com/api-keys
- Database credentials (if using local PostgreSQL)
- Other optional keys

### 3. Start Database (Docker)

```bash
# Start PostgreSQL and Redis
docker-compose up -d postgres redis

# Wait for services to be ready
sleep 5
```

### 4. Initialize Database

```bash
# Run migrations
source venv/bin/activate  # if not already active
alembic upgrade head
```

### 5. Verify Installation

```bash
# Test imports
python -c "from void.config import config; print('✅ Config loaded')"

# Test database connection
python -c "from void.data.models import Base; print('✅ Models loaded')"
```

## 🏃 Running the Agent

Once implementation is complete:

```bash
# Activate virtual environment
source venv/bin/activate

# Start the agent (Phase 1: Oracle Latency)
python -m void.agent --strategy oracle_latency

# Start with specific configuration
python -m void.agent --config configs/production.yaml --strategy oracle_latency

# Start in dry-run mode (no real trades)
python -m void.agent --dry-run --strategy oracle_latency
```

## 📊 Admin Dashboard

```bash
# Start admin API
uvicorn void.admin.api.app:app --reload --host 0.0.0.0 --port 8000

# Access dashboard
open http://localhost:8000
```

## 🔧 Development Commands

```bash
# Format code
black src/void/

# Run linter
ruff check src/void/ --fix

# Type checking
mypy src/void/

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=src/void --cov-report=html

# Run specific test
pytest tests/unit/test_config.py -v
```

## 📈 Monitoring

```bash
# Start monitoring services
docker-compose up -d prometheus grafana

# View metrics
open http://localhost:9090  # Prometheus
open http://localhost:3000  # Grafana (admin/admin)

# View logs
tail -f logs/agent/void.log
```

## 🗄️ Database Management

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history

# Reset database (DEV ONLY!)
alembic downgrade base
alembic upgrade head
```

## 🔍 Troubleshooting

### Import Errors

```bash
# Ensure you're in the virtual environment
which python  # Should show: /path/to/void/venv/bin/python

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

### Database Connection Issues

```bash
# Check if PostgreSQL is running
docker-compose ps

# View database logs
docker-compose logs postgres

# Restart database
docker-compose restart postgres
```

### Polymarket API Issues

```bash
# Verify credentials
python -c "
from void.config import config
print('API Key:', config.polymarket.api_key[:10] + '...')
print('CLOB URL:', config.polymarket.clob_url)
"

# Test connection (once client is implemented)
python -c "
from void.data.feeds.polymarket.clob_client import ClobClientWrapper
client = ClobClientWrapper()
print(client.get_order_book('some-token-id'))
"
```

## 📚 Project Structure

```
void/
├── .env                    # Environment variables
├── .env.example            # Environment template
├── requirements.txt        # Dependencies
├── README.md               # Full documentation
├── QUICKSTART.md           # This file
├── scripts/
│   └── setup.sh           # Setup script
├── src/void/
│   ├── __init__.py
│   ├── config.py          # ✅ Configuration
│   ├── data/
│   │   └── models.py      # ✅ Database models
│   ├── admin/             # Admin API
│   ├── accounts/          # Account management
│   ├── agent/             # Agent orchestration
│   ├── strategies/        # Trading strategies
│   ├── data/              # Data layer
│   ├── execution/         # Order execution
│   └── messaging/         # Event bus
├── alembic/               # Database migrations
├── tests/                 # Test suite
└── docker/                # Docker configuration
```

## 🎯 Next Steps

1. **Complete Foundation** (Current)
   - ✅ Configuration
   - ✅ Database models
   - ⏳ Database connection
   - ⏳ Alembic migrations

2. **Polymarket Integration** (Next)
   - CLOB client wrapper
   - Gamma API client
   - WebSocket client

3. **Strategy Implementation**
   - Oracle Latency detector
   - AI verifier
   - Order executor

4. **Testing & Deployment**
   - Unit tests
   - Integration tests
   - Docker deployment

## 📖 Additional Documentation

- `README.md` - Project overview and architecture
- `.claude/resources/VOID_CLAUDE_CODE_PROMPT.md` - Complete system spec
- `.claude/resources/Void-tactical-brief.md` - Implementation details
- `.claude/resources/dev-guide-Polymarket-autonomous-trading-agents.md` - API reference

## 💡 Tips

- Always activate the virtual environment before running commands
- Use `--dry-run` flag when testing new strategies
- Monitor logs in `logs/` directory
- Check Grafana dashboards for system health
- Join the team chat for updates

---

**Need Help?** Check the README.md or review the architecture docs in `.claude/resources/`
