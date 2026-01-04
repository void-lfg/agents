#!/usr/bin/env python3
"""Check database tables."""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from void.config import config

async def check_tables():
    """Check what tables exist."""
    engine = create_async_engine(str(config.database.url))

    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename;
        """))
        tables = result.fetchall()
        print("Existing tables:")
        for table in tables:
            print(f"  - {table[0]}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_tables())
