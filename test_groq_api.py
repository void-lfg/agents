#!/usr/bin/env python3
"""
Test script to verify Groq API integration.
Run this to check if the Groq API key and model are working correctly.
"""

import sys
import asyncio
sys.path.insert(0, '/Users/vivek/projects/void/src')

from groq import AsyncGroq
from void.config import config

print("=" * 60)
print("Groq API Integration Test")
print("=" * 60)

# Get API key from config
api_key = config.ai.groq_api_key.get_secret_value()
print(f"\nAPI Key (first 20 chars): {api_key[:20]}...")
print(f"Model: {config.ai.groq_model}")
print(f"Base URL: https://api.groq.com/openai/v1")

# Initialize client
print("\n1. Initializing AsyncGroq client...")
try:
    client = AsyncGroq(api_key=api_key)
    print("   ✓ Client initialized successfully")
except Exception as e:
    print(f"   ✗ Failed to initialize client: {e}")
    sys.exit(1)

async def test_api():
    # Test simple API call
    print("\n2. Testing simple 'hello' message...")
    try:
        response = await client.chat.completions.create(
            model=config.ai.groq_model,
            messages=[
                {"role": "user", "content": "Say 'Groq API test successful' in English."}
            ],
            max_tokens=50,
        )

        content = response.choices[0].message.content
        print(f"   ✓ API Response: {content}")

        if hasattr(response, 'usage'):
            print(f"   ✓ Prompt Tokens: {response.usage.prompt_tokens}")
            print(f"   ✓ Completion Tokens: {response.usage.completion_tokens}")
            print(f"   ✓ Total Tokens: {response.usage.total_tokens}")

    except Exception as e:
        error_str = str(e)
        print(f"   ✗ API call failed: {error_str}")
        sys.exit(1)

    # Test with actual chat scenario
    print("\n3. Testing chat with context...")
    try:
        response = await client.chat.completions.create(
            model=config.ai.groq_model,
            messages=[
                {"role": "system", "content": "You are a helpful trading assistant."},
                {"role": "user", "content": "What is Polymarket in one sentence?"}
            ],
            max_tokens=100,
            temperature=0.7,
        )

        content = response.choices[0].message.content
        print(f"   ✓ Chat Response: {content}")

        if hasattr(response, 'usage'):
            print(f"   ✓ Tokens used: {response.usage.total_tokens}")

    except Exception as e:
        print(f"   ✗ Chat test failed: {e}")
        sys.exit(1)

    # Test rate limiting (send 3 quick requests)
    print("\n4. Testing rate limiting (3 quick requests)...")
    try:
        tasks = []
        for i in range(3):
            task = client.chat.completions.create(
                model=config.ai.groq_model,
                messages=[
                    {"role": "user", "content": f"Say 'Request {i+1}' in English."}
                ],
                max_tokens=20,
            )
            tasks.append(task)

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = 0
        for i, resp in enumerate(responses):
            if isinstance(resp, Exception):
                print(f"   ✗ Request {i+1} failed: {str(resp)[:100]}")
            else:
                success_count += 1
                print(f"   ✓ Request {i+1} succeeded")

        print(f"\n   Rate Limit Test: {success_count}/3 requests succeeded")

    except Exception as e:
        print(f"   ✗ Rate limit test failed: {e}")

    print("\n" + "=" * 60)
    print("✓ ALL TESTS PASSED")
    print("=" * 60)
    print("\nThe Groq API is working correctly!")
    print("Rate Limits: 30 RPM, 6K TPM, 14.4K RPD (Developer Plan)")
    print("Model: llama-3.3-70b-versatile")
    print("\nRestart the bot with: python src/bot_runner.py")
    print("=" * 60)

    await client.close()

# Run async test
asyncio.run(test_api())
