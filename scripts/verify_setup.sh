#!/bin/bash

# VOID Trading Agent - Setup Verification Script

set -e

echo "🔍 VOID Trading Agent - Setup Verification"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check function
check() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✅${NC} $2"
    else
        echo -e "${RED}❌${NC} $2"
        return 1
    fi
}

warn() {
    echo -e "${YELLOW}⚠️  ${NC}$1"
}

# Track overall status
ALL_GOOD=0

# 1. Check Python version
echo "📌 Checking Python version..."
python3 --version > /dev/null 2>&1 && check 0 "Python installed" || { check 1 "Python not found"; ALL_GOOD=1; }

# 2. Check virtual environment
echo ""
echo "📌 Checking virtual environment..."
if [ -d "venv" ]; then
    check 0 "Virtual environment exists"
    source venv/bin/activate
    check 0 "Virtual environment activated"
else
    warn "Virtual environment not found - creating one..."
    python3 -m venv venv
    source venv/bin/activate
    check 0 "Virtual environment created and activated"
fi

# 3. Check dependencies
echo ""
echo "📌 Checking dependencies..."
pip list > /dev/null 2>&1 && check 0 "pip accessible" || { check 1 "pip not found"; ALL_GOOD=1; }

# Check critical packages
CRITICAL_PACKAGES="fastapi sqlalchemy pydantic httpx redis asyncpg"
for pkg in $CRITICAL_PACKAGES; do
    pip show $pkg > /dev/null 2>&1 && check 0 "$pkg installed" || { check 1 "$pkg missing"; ALL_GOOD=1; }
done

# 4. Check .env file
echo ""
echo "📌 Checking environment configuration..."
if [ -f ".env" ]; then
    check 0 ".env file exists"

    # Check critical variables
    grep -q "POLYMARKET_API_KEY=" .env && check 0 "Polymarket API key configured" || { check 1 "Polymarket API key missing"; ALL_GOOD=1; }
    grep -q "AI_ZAI_API_KEY=" .env && check 0 "Z.ai API key configured" || { check 1 "Z.ai API key missing"; ALL_GOOD=1; }
    grep -q "ENCRYPTION_KEY=" .env && check 0 "Encryption key configured" || { warn "Encryption key not set (generate one!)"; ALL_GOOD=1; }

    # Check if encryption key is default
    if grep -q "ENCRYPTION_KEY=your-32-byte" .env; then
        warn "⚠️  USING DEFAULT ENCRYPTION KEY! Generate a secure one:"
        echo "   python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        ALL_GOOD=1
    fi
else
    check 1 ".env file not found"
    ALL_GOOD=1
fi

# 5. Check Docker
echo ""
echo "📌 Checking Docker..."
docker --version > /dev/null 2>&1 && check 0 "Docker installed" || { check 1 "Docker not found"; ALL_GOOD=1; }
docker-compose --version > /dev/null 2>&1 && check 0 "Docker Compose installed" || { check 1 "Docker Compose not found"; ALL_GOOD=1; }

# 6. Check Docker services
echo ""
echo "📌 Checking Docker services..."
docker-compose ps > /dev/null 2>&1 && check 0 "Docker Compose accessible" || { check 1 "Docker Compose not accessible"; ALL_GOOD=1; }

# Check if services are running
if docker-compose ps | grep -q "Up"; then
    check 0 "Docker services running"
    docker-compose ps | grep "postgres.*Up" > /dev/null 2>&1 && check 0 "PostgreSQL running" || warn "PostgreSQL not running"
    docker-compose ps | grep "redis.*Up" > /dev/null 2>&1 && check 0 "Redis running" || warn "Redis not running"
else
    warn "No Docker services running (start with: docker-compose up -d postgres redis)"
fi

# 7. Check database connection
echo ""
echo "📌 Checking database..."
if docker-compose ps | grep -q "postgres.*Up"; then
    docker exec -it void-postgres psql -U void -d void -c "SELECT 1;" > /dev/null 2>&1 && check 0 "Database accessible" || { check 1 "Database not accessible"; ALL_GOOD=1; }
else
    warn "PostgreSQL not running - cannot check database"
fi

# 8. Check source files
echo ""
echo "📌 Checking source files..."
check_files=(
    "src/main.py"
    "src/void/config.py"
    "src/void/data/models.py"
    "src/void/strategies/oracle_latency/strategy.py"
    "src/void/strategies/oracle_latency/verifier.py"
    "src/void/agent/orchestrator.py"
    "src/void/execution/engine.py"
    "src/void/admin/api/app.py"
)

for file in "${check_files[@]}"; do
    [ -f "$file" ] && check 0 "$file exists" || { check 1 "$file missing"; ALL_GOOD=1; }
done

# 9. Check logs directory
echo ""
echo "📌 Checking logs directory..."
mkdir -p logs/agent && check 0 "Logs directory created" || { check 1 "Cannot create logs directory"; ALL_GOOD=1; }

# 10. Try importing main modules
echo ""
echo "📌 Checking Python imports..."
python -c "import void.config" 2>/dev/null && check 0 "void.config imports" || { check 1 "void.config import failed"; ALL_GOOD=1; }
python -c "import void.data.models" 2>/dev/null && check 0 "void.data.models imports" || { check 1 "void.data.models import failed"; ALL_GOOD=1; }
python -c "import void.strategies.oracle_latency" 2>/dev/null && check 0 "oracle_latency imports" || { check 1 "oracle_latency import failed"; ALL_GOOD=1; }

# 11. Check Alembic
echo ""
echo "📌 Checking database migrations..."
[ -d "alembic" ] && check 0 "Alembic directory exists" || { check 1 "Alembic directory missing"; ALL_GOOD=1; }
[ -f "alembic.ini" ] && check 0 "alembic.ini exists" || { check 1 "alembic.ini missing"; ALL_GOOD=1; }

# Final summary
echo ""
echo "=========================================="
if [ $ALL_GOOD -eq 0 ]; then
    echo -e "${GREEN}✅ ALL CHECKS PASSED!${NC}"
    echo ""
    echo "🚀 You're ready to start trading!"
    echo ""
    echo "Next steps:"
    echo "  1. Ensure PostgreSQL and Redis are running:"
    echo "     docker-compose up -d postgres redis"
    echo ""
    echo "  2. Run database migrations:"
    echo "     alembic upgrade head"
    echo ""
    echo "  3. Start the agent:"
    echo "     python src/main.py"
    echo ""
else
    echo -e "${RED}❌ SOME CHECKS FAILED${NC}"
    echo ""
    echo "Please fix the issues above before running the agent."
    echo ""
    echo "Common fixes:"
    echo "  - Generate encryption key: python3 -c \"import secrets; print(secrets.token_urlsafe(32))\""
    echo "  - Install dependencies: pip install -r requirements.txt"
    echo "  - Start Docker services: docker-compose up -d postgres redis"
    echo "  - Run migrations: alembic upgrade head"
    echo ""
fi

echo "=========================================="

exit $ALL_GOOD
