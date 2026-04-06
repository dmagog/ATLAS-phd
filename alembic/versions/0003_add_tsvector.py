"""add tsvector column and GIN index to chunks for hybrid retrieval

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add tsvector column
    op.execute(
        "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS text_search_vec TSVECTOR"
    )
    # Backfill existing chunks (multilingual — 'simple' works for both RU and EN)
    op.execute(
        "UPDATE chunks SET text_search_vec = to_tsvector('simple', text)"
    )
    # GIN index for fast FTS
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING GIN(text_search_vec)"
    )
    # Trigger keeps the column in sync on insert/update
    op.execute("""
        CREATE OR REPLACE FUNCTION chunks_tsv_update() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.text_search_vec := to_tsvector('simple', NEW.text);
            RETURN NEW;
        END;
        $$
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_chunks_tsv ON chunks")
    op.execute("""
        CREATE TRIGGER trg_chunks_tsv
            BEFORE INSERT OR UPDATE OF text ON chunks
            FOR EACH ROW EXECUTE FUNCTION chunks_tsv_update()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_chunks_tsv ON chunks")
    op.execute("DROP FUNCTION IF EXISTS chunks_tsv_update()")
    op.execute("DROP INDEX IF EXISTS idx_chunks_tsv")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS text_search_vec")
