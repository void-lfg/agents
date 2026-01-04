"""
Telegram Bot Configuration
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramBotConfig(BaseSettings):
    """Telegram bot configuration."""

    model_config = SettingsConfigDict(env_prefix="TELEGRAM_", extra="ignore")

    token: str = Field(..., description="Telegram bot token")
    webhook_url: str | None = Field(None, description="Webhook URL for production")
    allowed_user_ids: list[int] = Field(
        default=[],
        description="List of allowed Telegram user IDs (empty = all users allowed)"
    )
    admin_user_ids: list[int] = Field(
        default=[],
        description="List of admin user IDs who can control agents"
    )
    notify_on_signal: bool = Field(
        default=True,
        description="Send notifications when signals are detected"
    )
    notify_on_trade: bool = Field(
        default=True,
        description="Send notifications when trades are executed"
    )
    notify_on_error: bool = Field(
        default=True,
        description="Send notifications on errors"
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level for bot"
    )
