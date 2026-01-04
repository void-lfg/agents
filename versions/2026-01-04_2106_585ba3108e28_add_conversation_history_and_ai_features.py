"""add conversation history and AI features

Revision ID: 585ba3108e28
Revises:
Create Date: 2026-01-04 21:06:42.623367+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '585ba3108e28'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create conversation_history table
    op.create_table(
        'conversation_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('messages', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_conv_history_user', 'conversation_history', ['user_id'])
    op.create_index('idx_conv_history_updated', 'conversation_history', ['updated_at'])

    # Create twitter_data table
    op.create_table(
        'twitter_data',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('tweet_id', sa.String(50), nullable=False, unique=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('author', sa.String(100), nullable=True),
        sa.Column('author_id', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('collected_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('market_id', sa.String(50), nullable=True),
        sa.Column('sentiment_score', sa.Float(), nullable=True),
        sa.Column('embedding', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('public_metrics', sa.JSON(), nullable=True),
        sa.Column('extra_data', sa.JSON(), nullable=True, server_default='{}'),
    )
    op.create_index('idx_twitter_tweet_id', 'twitter_data', ['tweet_id'])
    op.create_index('idx_twitter_market', 'twitter_data', ['market_id'])
    op.create_index('idx_twitter_sentiment', 'twitter_data', ['sentiment_score'])
    op.create_index('idx_twitter_collected', 'twitter_data', ['collected_at'])

    # Create knowledge_base table
    op.create_table(
        'knowledge_base',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('market_id', sa.String(50), nullable=False),
        sa.Column('content_type', sa.String(20), nullable=False),  # 'news', 'tweet', 'analysis'
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('source_url', sa.String(500), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True, server_default='{}'),
        sa.Column('embedding', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('collected_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('archived_at', sa.DateTime(), nullable=True),
    )
    op.create_index('idx_knowledge_market', 'knowledge_base', ['market_id'])
    op.create_index('idx_knowledge_type', 'knowledge_base', ['content_type'])
    op.create_index('idx_knowledge_collected', 'knowledge_base', ['collected_at'])


def downgrade() -> None:
    op.drop_table('knowledge_base')
    op.drop_table('twitter_data')
    op.drop_table('conversation_history')
