"""add qa_feedback table

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS qa_feedback (
            id          UUID PRIMARY KEY,
            user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            request_id  VARCHAR(64) NOT NULL,
            rating      VARCHAR(16) NOT NULL,
            question_text    TEXT,
            answer_markdown  TEXT,
            created_at  TIMESTAMP NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_qa_feedback_request_id ON qa_feedback (request_id)"
    )


def downgrade() -> None:
    op.drop_index('ix_qa_feedback_request_id', table_name='qa_feedback')
    op.drop_table('qa_feedback')
