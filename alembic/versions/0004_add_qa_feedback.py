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
    op.create_table(
        'qa_feedback',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('request_id', sa.String(64), nullable=False, index=True),
        sa.Column('rating', sa.String(16), nullable=False),
        sa.Column('question_text', sa.Text, nullable=True),
        sa.Column('answer_markdown', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index('ix_qa_feedback_request_id', 'qa_feedback', ['request_id'])


def downgrade() -> None:
    op.drop_index('ix_qa_feedback_request_id', table_name='qa_feedback')
    op.drop_table('qa_feedback')
