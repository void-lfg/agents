#!/bin/bash

# VOID Trading Agent - Setup Script
# This script sets up the development environment

set -e  # Exit on error

echo "🏗️  VOID Trading Agent - Setup Script"
echo "======================================"
echo ""

# Check Python version
echo "📋 Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_version="3.11"

if [[ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]]; then
    echo "❌ Python 3.11+ required. Current: $python_version"
    exit 1
fi
echo "✅ Python version: $python_version"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "🔧 Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment exists"
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📦 Installing dependencies..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo "✅ Production dependencies installed"
else
    echo "❌ requirements.txt not found"
    exit 1
fi

# Install dev dependencies
if [ -f "requirements-dev.txt" ]; then
    echo "📦 Installing development dependencies..."
    pip install -r requirements-dev.txt
    echo "✅ Development dependencies installed"
fi

# Check .env file
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found"
    if [ -f ".env.example" ]; then
        echo "📋 Creating .env from .env.example..."
        cp .env.example .env
        echo "⚠️  PLEASE EDIT .env WITH YOUR CREDENTIALS BEFORE CONTINUING"
    fi
else
    echo "✅ .env file exists"
fi

# Create logs directory
mkdir -p logs
echo "✅ Logs directory created"

# Create necessary directories
echo "📁 Creating project directories..."
mkdir -p logs/agent
mkdir -p logs/api
mkdir -p logs/execution
echo "✅ Directories created"

# Initialize Alembic if not already done
if [ ! -d "alembic" ]; then
    echo "🗄️  Initializing Alembic..."
    cd src
    alembic init ../alembic
    cd ..
    echo "✅ Alembic initialized"
else
    echo "✅ Alembic already initialized"
fi

# Format code with black
if command -v black &> /dev/null; then
    echo "🎨 Formatting code with black..."
    black src/void/
    echo "✅ Code formatted"
fi

# Run linting with ruff
if command -v ruff &> /dev/null; then
    echo "🔍 Running ruff linter..."
    ruff check src/void/ --fix
    echo "✅ Linting complete"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env with your API credentials"
echo "2. Initialize database: alembic upgrade head"
echo "3. Start services: docker-compose up -d"
echo "4. Run agent: python -m void.agent"
echo ""
echo "For development:"
echo "- Activate venv: source venv/bin/activate"
echo "- Run tests: pytest"
echo "- Format code: black src/"
echo "- Type check: mypy src/"
echo ""
