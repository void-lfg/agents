"""add_ai_features

Revision ID: 9e420bde7866
Revises: 
Create Date: 2026-01-04 17:15:55.065751+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9e420bde7866'
down_revision: Union[str, None] = '1c3b1aa5f5b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create conversation_history table
    op.create_table(
        'conversation_history',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('messages', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_conv_history_user', 'conversation_history', ['user_id'])
    op.create_index('idx_conv_history_updated', 'conversation_history', ['updated_at'])

    # Create twitter_data table
    op.create_table(
        'twitter_data',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tweet_id', sa.String(length=50), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('author', sa.String(length=100), nullable=True),
        sa.Column('author_id', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('collected_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('market_id', sa.String(length=100), nullable=True),
        sa.Column('sentiment_score', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('public_metrics', sa.JSON(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tweet_id')
    )
    op.create_index('idx_twitter_market', 'twitter_data', ['market_id'])
    op.create_index('idx_twitter_collected', 'twitter_data', ['collected_at'])
    op.create_index('idx_twitter_sentiment', 'twitter_data', ['sentiment_score'])

    # Create market_knowledge table
    op.create_table(
        'market_knowledge',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('market_id', sa.String(length=100), nullable=False),
        sa.Column('content_type', sa.String(length=50), nullable=False),
        sa.Column('source_url', sa.String(length=500), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('relevance_score', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('collected_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('r2_url', sa.String(length=1000), nullable=True),
        sa.Column('archived_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_knowledge_market', 'market_knowledge', ['market_id'])
    op.create_index('idx_knowledge_type', 'market_knowledge', ['content_type'])
    op.create_index('idx_knowledge_relevance', 'market_knowledge', ['relevance_score'])
    op.create_index('idx_knowledge_collected', 'market_knowledge', ['collected_at'])

    # Create sentiment_scores table
    op.create_table(
        'sentiment_scores',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('entity_id', sa.String(length=100), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('score', sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column('confidence', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('analyzed_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_sentiment_entity', 'sentiment_scores', ['entity_id', 'entity_type'])
    op.create_index('idx_sentiment_analyzed', 'sentiment_scores', ['analyzed_at'])

    # Add columns to markets table
    op.add_column('markets', sa.Column('knowledge_data', sa.JSON(), nullable=True))
    op.add_column('markets', sa.Column('last_researched_at', sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column('markets', sa.Column('sentiment_score', sa.Numeric(precision=5, scale=4), nullable=True))
    op.add_column('markets', sa.Column('twitter_volume', sa.Integer(), nullable=True))
    op.add_column('markets', sa.Column('news_count', sa.Integer(), nullable=True))

    # Create indexes for new market columns
    op.create_index('idx_markets_sentiment', 'markets', ['sentiment_score'])
    op.create_index('idx_markets_researched', 'markets', ['last_researched_at'])


def downgrade() -> None:
    # Remove indexes from markets
    op.drop_index('idx_markets_researched', 'markets')
    op.drop_index('idx_markets_sentiment', 'markets')

    # Remove columns from markets table
    op.drop_column('markets', 'news_count')
    op.drop_column('markets', 'twitter_volume')
    op.drop_column('markets', 'sentiment_score')
    op.drop_column('markets', 'last_researched_at')
    op.drop_column('markets', 'knowledge_data')

    # Drop sentiment_scores table
    op.drop_index('idx_sentiment_analyzed', 'sentiment_scores')
    op.drop_index('idx_sentiment_entity', 'sentiment_scores')
    op.drop_table('sentiment_scores')

    # Drop market_knowledge table
    op.drop_index('idx_knowledge_collected', 'market_knowledge')
    op.drop_index('idx_knowledge_relevance', 'market_knowledge')
    op.drop_index('idx_knowledge_type', 'market_knowledge')
    op.drop_index('idx_knowledge_market', 'market_knowledge')
    op.drop_table('market_knowledge')

    # Drop twitter_data table
    op.drop_index('idx_twitter_sentiment', 'twitter_data')
    op.drop_index('idx_twitter_collected', 'twitter_data')
    op.drop_index('idx_twitter_market', 'twitter_data')
    op.drop_table('twitter_data')

    # Drop conversation_history table
    op.drop_index('idx_conv_history_updated', 'conversation_history')
    op.drop_index('idx_conv_history_user', 'conversation_history')
    op.drop_table('conversation_history')
