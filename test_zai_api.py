#!/usr/bin/env python3
"""
Test script to verify Z.ai API key is working with zai-sdk.
Run this to check if the API key has valid balance/quota.
"""

import sys
import asyncio
sys.path.insert(0, '/Users/vivek/projects/void/src')

from zai import ZaiClient
from void.config import config

print("=" * 60)
print("Z.ai API Key Test (zai-sdk)")
print("=" * 60)

# Get API key from config
api_key = config.ai.zai_api_key.get_secret_value()
print(f"\nAPI Key (first 20 chars): {api_key[:20]}...")
print(f"Model: {config.ai.zai_model}")

# Initialize client
print("\n1. Initializing ZaiClient...")
try:
    client = ZaiClient(api_key=api_key)
    print("   ✓ Client initialized successfully")
except Exception as e:
    print(f"   ✗ Failed to initialize client: {e}")
    sys.exit(1)

# Test simple API call
print("\n2. Testing simple 'hello' message...")
try:
    response = client.chat.completions.create(
        model=config.ai.zai_model,
        messages=[
            {"role": "user", "content": "Say 'API test successful' in English."}
        ],
        max_tokens=50,
    )

    content = response.choices[0].message.content
    print(f"   ✓ API Response: {content}")

    if hasattr(response, 'usage'):
        print(f"   ✓ Tokens used: {response.usage.total_tokens}")

except Exception as e:
    error_str = str(e)
    print(f"   ✗ API call failed: {error_str}")

    # Check for specific error codes
    if "余额不足" in error_str or "insufficient" in error_str.lower() or "balance" in error_str.lower():
        print("\n" + "=" * 60)
        print("ERROR: API Balance Issue")
        print("=" * 60)
        print("\nThe API key does not have sufficient balance/quota.")
        print("\nPossible solutions:")
        print("1. Log into https://api.z.ai/")
        print("2. Check your account balance and billing status")
        print("3. Verify your plan is active")
        print("4. Check if this API key is associated with the correct account")
        print("\nThe bot code is correctly integrated - this is an account/billing issue.")
        print("=" * 60)

    elif "429" in error_str or "rate" in error_str.lower():
        print("\nRate limit exceeded. The API key may have hit concurrency limits.")
        print("Wait a moment and try again.")

    elif "401" in error_str or "auth" in error_str.lower() or "unauthorized" in error_str.lower():
        print("\nAuthentication failed. Check if the API key is correct.")

    sys.exit(1)

# Test with actual chat scenario
print("\n3. Testing chat with context...")
try:
    response = client.chat.completions.create(
        model=config.ai.zai_model,
        messages=[
            {"role": "system", "content": "You are a helpful trading assistant."},
            {"role": "user", "content": "What is Polymarket?"}
        ],
        max_tokens=100,
        temperature=0.7,
    )

    content = response.choices[0].message.content
    print(f"   ✓ Chat Response: {content[:100]}...")

    if hasattr(response, 'usage'):
        print(f"   ✓ Tokens used: {response.usage.total_tokens}")

except Exception as e:
    print(f"   ✗ Chat test failed: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✓ ALL TESTS PASSED")
print("=" * 60)
print("\nThe API key is working correctly!")
print("The bot should now be able to respond to messages.")
print("\nRestart the bot with: python src/bot_runner.py")
print("=" * 60)
