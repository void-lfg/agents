"""add_ai_features_to_markets_table

Revision ID: dc04e81266ae
Revises: 585ba3108e28
Create Date: 2026-01-04 21:22:54.177888+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'dc04e81266ae'
down_revision: Union[str, None] = '585ba3108e28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add AI/Knowledge columns to markets table
    op.add_column('markets', sa.Column('knowledge_data', postgresql.JSONB(), nullable=True, server_default='{}'))
    op.add_column('markets', sa.Column('last_researched_at', sa.DateTime(), nullable=True))
    op.add_column('markets', sa.Column('sentiment_score', sa.Numeric(precision=5, scale=4), nullable=True))
    op.add_column('markets', sa.Column('twitter_volume', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('markets', sa.Column('news_count', sa.Integer(), nullable=True, server_default='0'))

    # Create indexes for AI features
    op.create_index('idx_markets_sentiment', 'markets', ['sentiment_score'])
    op.create_index('idx_markets_last_researched', 'markets', ['last_researched_at'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_markets_last_researched', 'markets')
    op.drop_index('idx_markets_sentiment', 'markets')

    # Drop columns
    op.drop_column('markets', 'news_count')
    op.drop_column('markets', 'twitter_volume')
    op.drop_column('markets', 'sentiment_score')
    op.drop_column('markets', 'last_researched_at')
    op.drop_column('markets', 'knowledge_data')
