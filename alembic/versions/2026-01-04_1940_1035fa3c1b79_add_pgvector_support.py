"""add_pgvector_support

Revision ID: 1035fa3c1b79
Revises: 9e420bde7866
Create Date: 2026-01-04 19:40:58.912294+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1035fa3c1b79'
down_revision: Union[str, None] = '9e420bde7866'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension (Neon has this pre-installed)
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # Add embedding column to market_knowledge for semantic search
    op.add_column('market_knowledge', sa.Column('embedding', sa.ARRAY(sa.Float), nullable=True))

    # Create vector similarity index using ivfflat (faster for large datasets)
    # Note: ivfflat requires enough rows - we'll use HNSW if available, otherwise fallback
    try:
        # Try HNSW index (faster, better recall)
        op.execute('''
            CREATE INDEX idx_knowledge_embedding_hnsw
            ON market_knowledge
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        ''')
    except Exception:
        # Fallback to ivfflat if HNSW not available
        try:
            op.execute('''
                CREATE INDEX idx_knowledge_embedding_ivfflat
                ON market_knowledge
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
            ''')
        except Exception:
            # Final fallback - no vector index (just sequential scan)
            pass

    # Add embedding column to twitter_data for tweet search
    op.add_column('twitter_data', sa.Column('embedding', sa.ARRAY(sa.Float), nullable=True))


def downgrade() -> None:
    # Drop embedding columns
    op.drop_column('twitter_data', 'embedding')
    op.drop_column('market_knowledge', 'embedding')

    # Note: We don't drop the extension as it might be used elsewhere
