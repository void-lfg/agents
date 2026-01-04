"""add_missing_ai_tables

Revision ID: fbc80b132d8b
Revises: dc04e81266ae
Create Date: 2026-01-04 21:24:31.882761+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'fbc80b132d8b'
down_revision: Union[str, None] = 'dc04e81266ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create sentiment_scores table (this one is actually missing)
    op.create_table(
        'sentiment_scores',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('entity_id', sa.String(100), nullable=False),  # market ID, tweet ID, etc.
        sa.Column('entity_type', sa.String(50), nullable=False),  # market, tweet, news
        sa.Column('score', sa.Numeric(precision=5, scale=4), nullable=False),  # -1.0 to +1.0
        sa.Column('confidence', sa.Numeric(precision=5, scale=4), nullable=True),  # 0.0 to 1.0
        sa.Column('source', sa.String(50), nullable=True),  # groq, openai, etc.
        sa.Column('analyzed_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('metadata', postgresql.JSONB(), nullable=True, server_default='{}'),
    )
    op.create_index('idx_sentiment_entity', 'sentiment_scores', ['entity_id', 'entity_type'])
    op.create_index('idx_sentiment_analyzed', 'sentiment_scores', ['analyzed_at'])
    op.create_index('idx_sentiment_score', 'sentiment_scores', ['score'])


def downgrade() -> None:
    # Drop tables
    op.drop_table('sentiment_scores')
