"""
Global configuration using Pydantic Settings.
All secrets loaded from environment variables.
"""

from dotenv import load_dotenv
from typing import Literal, Optional
from pydantic import Field, SecretStr, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file
load_dotenv()


class DatabaseConfig(BaseSettings):
    """Database configuration."""

    model_config = SettingsConfigDict(env_prefix="DB_", extra="ignore")

    url: PostgresDsn = Field(
        default="postgresql+asyncpg://void:void_password@localhost:5432/void",
        description="PostgreSQL connection URL"
    )
    pool_size: int = Field(default=10, description="Connection pool size")
    max_overflow: int = Field(default=20, description="Max overflow connections")
    echo: bool = Field(default=False, description="Echo SQL queries")


class RedisConfig(BaseSettings):
    """Redis configuration."""

    model_config = SettingsConfigDict(env_prefix="REDIS_", extra="ignore")

    url: RedisDsn = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )
    max_connections: int = Field(default=100, description="Max connections")


class PolygonConfig(BaseSettings):
    """Polygon blockchain configuration."""

    model_config = SettingsConfigDict(env_prefix="POLYGON_", extra="ignore")

    rpc_url: str = Field(
        default="https://polygon-rpc.com",
        description="Polygon RPC endpoint"
    )
    chain_id: int = Field(default=137, description="Polygon chain ID")
    gas_price_multiplier: float = Field(
        default=1.1,
        description="Gas price multiplier"
    )


class PolymarketConfig(BaseSettings):
    """Polymarket API configuration."""

    model_config = SettingsConfigDict(env_prefix="POLYMARKET_", extra="ignore")

    clob_url: str = Field(
        default="https://clob.polymarket.com",
        description="CLOB API base URL"
    )
    gamma_url: str = Field(
        default="https://gamma-api.polymarket.com",
        description="Gamma API base URL"
    )
    ws_url: str = Field(
        default="wss://ws-subscriptions-clob.polymarket.com/ws/market",
        description="WebSocket URL"
    )

    # API credentials (from environment)
    api_key: str = Field(..., description="Polymarket API key")
    api_secret: SecretStr = Field(..., description="Polymarket API secret")
    api_passphrase: SecretStr = Field(..., description="Polymarket API passphrase")

    # Rate limits
    order_burst_limit: int = Field(default=240, description="Burst rate limit")
    order_sustained_limit: int = Field(default=40, description="Sustained rate limit")


class TradingConfig(BaseSettings):
    """Trading strategy configuration."""

    model_config = SettingsConfigDict(env_prefix="TRADING_", extra="ignore")

    max_position_size_usd: float = Field(
        default=500.0,
        description="Max position size per trade"
    )
    max_total_exposure_usd: float = Field(
        default=5000.0,
        description="Max total exposure"
    )
    min_profit_margin: float = Field(
        default=0.01,
        description="Minimum profit margin (1%)"
    )
    max_slippage: float = Field(default=0.02, description="Max slippage (2%)")
    cooldown_seconds: int = Field(default=60, description="Cooldown between trades")


class AIConfig(BaseSettings):
    """Multi-LLM provider configuration."""

    model_config = SettingsConfigDict(env_prefix="AI_", extra="ignore")

    # LLM Provider Selection
    llm_provider: str = Field(default="groq", description="LLM provider: groq | deepseek | openai")

    # Groq Configuration
    groq_api_key: SecretStr = Field(default=SecretStr(""), description="Groq API key")
    groq_model: str = Field(default="llama-3.3-70b-versatile", description="Groq model")

    # DeepSeek Configuration
    deepseek_api_key: SecretStr = Field(default=SecretStr(""), description="DeepSeek API key")
    deepseek_model: str = Field(default="deepseek-chat", description="DeepSeek model")

    # OpenAI Configuration
    openai_api_key: SecretStr = Field(default=SecretStr(""), description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI model")

    # Legacy Z.ai (deprecated, keeping for compatibility)
    zai_api_key: SecretStr = Field(default=SecretStr(""), description="Z.ai API key (deprecated)")
    zai_model: str = Field(default="glm-4.7", description="Z.ai GLM model (deprecated)")

    confidence_threshold: float = Field(
        default=0.95,
        description="AI confidence threshold"
    )

    # Chat settings
    chat_enabled: bool = Field(default=True, description="Enable AI chat feature")
    chat_max_history: int = Field(default=10, description="Max conversation history")
    chat_temperature: float = Field(default=0.7, description="Chat temperature (0-1)")
    chat_max_tokens: int = Field(default=2000, description="Max tokens per response")
    chat_timeout_seconds: int = Field(default=10, description="Chat request timeout")


class AdminConfig(BaseSettings):
    """Admin API configuration."""

    model_config = SettingsConfigDict(env_prefix="ADMIN_", extra="ignore")

    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    jwt_secret: SecretStr = Field(..., description="JWT secret")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_expiry_hours: int = Field(default=24, description="JWT token expiry")
    api_key_header: str = Field(
        default="X-API-Key",
        description="API key header name"
    )


class EncryptionConfig(BaseSettings):
    """Encryption configuration."""

    model_config = SettingsConfigDict(env_prefix="ENCRYPTION_", extra="ignore")

    key: str = Field(..., description="Encryption key (32 bytes)")


class MonitoringConfig(BaseSettings):
    """Monitoring configuration."""

    model_config = SettingsConfigDict(env_prefix="PROMETHEUS_", extra="ignore")

    port: int = Field(default=9090, description="Prometheus port")
    grafana_password: str = Field(default="admin", description="Grafana password")


class TwitterConfig(BaseSettings):
    """Twitter/X API configuration."""

    model_config = SettingsConfigDict(env_prefix="TWITTER_", extra="ignore")

    bearer_token: SecretStr = Field(..., description="Twitter bearer token")
    api_key: SecretStr = Field(..., description="Twitter API key")
    api_secret: SecretStr = Field(..., description="Twitter API secret")

    # Collection settings
    collection_interval_minutes: int = Field(default=15, description="Data collection interval")
    trends_interval_hours: int = Field(default=1, description="Trends monitoring interval")
    search_max_results: int = Field(default=100, description="Max results per search")
    sentiment_enabled: bool = Field(default=True, description="Enable sentiment analysis")


class R2Config(BaseSettings):
    """Cloudflare R2 storage configuration."""

    model_config = SettingsConfigDict(env_prefix="R2_", extra="ignore")

    account_id: str = Field(..., description="Cloudflare account ID")
    access_key_id: str = Field(..., description="R2 access key ID")
    secret_access_key: SecretStr = Field(..., description="R2 secret access key")
    bucket_name: str = Field(default="void-v1", description="R2 bucket name")
    knowledge_base_path: str = Field(
        default="void-agent-knowledge-base",
        description="Knowledge base path in bucket"
    )
    endpoint: str = Field(
        default="https://476f3d30838d09d1253b76f0c92c265d.r2.cloudflarestorage.com",
        description="R2 S3-compatible endpoint"
    )


class KnowledgeConfig(BaseSettings):
    """Knowledge base configuration."""

    model_config = SettingsConfigDict(env_prefix="KNOWLEDGE_", extra="ignore")

    retention_days: int = Field(default=20, description="Hot storage retention period")
    archival_enabled: bool = Field(default=True, description="Enable archival to R2")
    auto_research: bool = Field(default=True, description="Auto-research markets")
    max_knowledge_per_market: int = Field(
        default=1000,
        description="Max knowledge entries per market"
    )


class VoidConfig(BaseSettings):
    """Master configuration aggregating all sub-configs."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    environment: Literal["development", "staging", "production"] = Field(
        default="development"
    )
    debug: bool = Field(default=False)

    # Sub-configurations
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    polygon: PolygonConfig = Field(default_factory=PolygonConfig)
    polymarket: PolymarketConfig = Field(default_factory=PolymarketConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    admin: AdminConfig = Field(default_factory=AdminConfig)
    encryption: EncryptionConfig = Field(default_factory=EncryptionConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    twitter: TwitterConfig = Field(default_factory=TwitterConfig)
    r2: R2Config = Field(default_factory=R2Config)
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)


# Global config instance
config = VoidConfig()


__all__ = [
    "VoidConfig",
    "DatabaseConfig",
    "RedisConfig",
    "PolygonConfig",
    "PolymarketConfig",
    "TradingConfig",
    "AIConfig",
    "AdminConfig",
    "EncryptionConfig",
    "MonitoringConfig",
    "TwitterConfig",
    "R2Config",
    "KnowledgeConfig",
    "config",
]
