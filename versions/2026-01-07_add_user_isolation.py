"""Add telegram_user_id to accounts and agents for user isolation.

Revision ID: a1b2c3d4e5f6
Revises: 1035fa3c1b79
Create Date: 2026-01-07

CRITICAL: This migration adds user isolation to prevent data sharing between users.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "fbc80b132d8b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add telegram_user_id to accounts table
    op.add_column(
        "accounts",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
    )

    # Add telegram_user_id to agents table
    op.add_column(
        "agents",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
    )

    # Create indexes for fast lookups
    op.create_index(
        "ix_accounts_telegram_user_id",
        "accounts",
        ["telegram_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_agents_telegram_user_id",
        "agents",
        ["telegram_user_id"],
        unique=False,
    )

    # Remove the old unique constraint on name (was globally unique)
    op.drop_constraint("accounts_name_key", "accounts", type_="unique")
    op.drop_constraint("agents_name_key", "agents", type_="unique")

    # Add new unique constraint: name unique per user
    op.create_unique_constraint(
        "uq_account_user_name",
        "accounts",
        ["telegram_user_id", "name"],
    )
    op.create_unique_constraint(
        "uq_agent_user_name",
        "agents",
        ["telegram_user_id", "name"],
    )


def downgrade() -> None:
    # Drop new constraints
    op.drop_constraint("uq_account_user_name", "accounts", type_="unique")
    op.drop_constraint("uq_agent_user_name", "agents", type_="unique")

    # Restore old unique constraints
    op.create_unique_constraint("accounts_name_key", "accounts", ["name"])
    op.create_unique_constraint("agents_name_key", "agents", ["name"])

    # Drop indexes
    op.drop_index("ix_accounts_telegram_user_id", table_name="accounts")
    op.drop_index("ix_agents_telegram_user_id", table_name="agents")

    # Drop columns
    op.drop_column("accounts", "telegram_user_id")
    op.drop_column("agents", "telegram_user_id")
