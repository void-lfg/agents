#!/usr/bin/env python3
"""Create all database tables directly."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from void.data.database import engine
from void.data.models import Base

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("✅ All tables created successfully")

if __name__ == "__main__":
    asyncio.run(main())
