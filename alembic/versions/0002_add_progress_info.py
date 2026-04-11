"""add progress_info to ingestion_jobs

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'ingestion_jobs',
        sa.Column('progress_info', postgresql.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('ingestion_jobs', 'progress_info')
