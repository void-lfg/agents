"""VOID Trading Agent - Setup configuration"""

from setuptools import setup, find_packages

setup(
    name="void-trading-agent",
    version="1.0.0",
    description="Autonomous trading agent for Polymarket prediction markets",
    author="VOID Team",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "aiohttp>=3.9.3",
        "aiofiles>=23.2.1",
        "asyncpg>=0.29.0",
        "python-dotenv>=1.0.1",
        "fastapi>=0.109.0",
        "uvicorn[standard]>=0.27.0",
        "sqlalchemy[asyncio]>=2.0.25",
        "alembic>=1.13.1",
        "redis>=5.0.1",
        "web3>=6.18.0",
        "eth-account>=0.13.0",
        "py-clob-client>=0.34.0",
        "httpx[http2]>=0.27.0",
        "pydantic>=2.6.1",
        "pydantic-settings>=2.1.0",
        "structlog>=24.1.0",
        "prometheus-client>=0.20.0",
        "websockets>=12.0",
        "cryptography>=42.0.2",
        "tenacity>=8.2.3",
        "click>=8.1.7",
        "tabulate>=0.9.0",
        "rich>=13.7.0",
    ],
    entry_points={
        "console_scripts": [
            "void-admin=void.admin.cli.main:cli",
        ],
    },
    python_requires=">=3.11",
)
