#!/bin/bash

# VOID Trading Agent - Test Runner

set -e

echo "🧪 VOID Trading Agent - Test Runner"
echo "=================================="
echo ""

# Check virtual environment
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Run setup.sh first."
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Run tests with coverage
echo "🔬 Running tests..."
pytest tests/ \
    -v \
    --cov=src/void \
    --cov-report=html \
    --cov-report=term-missing \
    --cov-fail-under=80 \
    "$@"

echo ""
echo "✅ Tests complete!"
echo ""
echo "📊 Coverage report: htmlcov/index.html"
echo ""
