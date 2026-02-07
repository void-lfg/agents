#!/bin/bash

# VOID Telegram Bot Start Script
# Usage: ./start_tg.sh

echo "🤖 Starting VOID Telegram Bot..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Creating..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
fi

# Activate virtual environment
source venv/bin/activate

# Kill existing bot instances (if any)
echo "🧹 Cleaning up existing instances..."
pkill -f "bot_runner.py" 2>/dev/null || true

# Wait a moment for cleanup
sleep 2

# Start the bot
echo "🚀 Starting bot in polling mode..."
./venv/bin/python src/bot_runner.py
