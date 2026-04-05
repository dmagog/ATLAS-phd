"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('role', sa.Enum('user', 'admin', name='userrole'), nullable=False, server_default='user'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )

    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('title', sa.String(512), nullable=False),
        sa.Column('filename', sa.String(512), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False, unique=True),
        sa.Column('file_path', sa.String(1024), nullable=False),
        sa.Column('mime_type', sa.String(128), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )

    op.create_table(
        'chunks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('section', sa.String(512), nullable=True),
        sa.Column('page', sa.Integer(), nullable=True),
        sa.Column('embedding', Vector(384), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('document_id', 'chunk_index', name='uq_chunk_doc_index'),
    )
    op.create_index('idx_chunks_embedding', 'chunks', ['embedding'], postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})

    op.create_table(
        'ingestion_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('status', sa.String(32), nullable=False, server_default='created'),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('accepted_files', postgresql.JSON(), nullable=False, server_default='[]'),
        sa.Column('rejected_files', postgresql.JSON(), nullable=False, server_default='[]'),
    )

    op.create_table(
        'sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('mode', sa.String(32), nullable=False, server_default='qa'),
        sa.Column('response_profile', sa.String(32), nullable=False, server_default='detailed'),
        sa.Column('history', postgresql.JSON(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )

    op.create_table(
        'selfcheck_attempts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('topic', sa.String(512), nullable=False),
        sa.Column('language', sa.String(8), nullable=False, server_default='ru'),
        sa.Column('status', sa.String(32), nullable=False, server_default='created'),
        sa.Column('question_set', postgresql.JSON(), nullable=True),
        sa.Column('answers', postgresql.JSON(), nullable=True),
        sa.Column('evaluation', postgresql.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('selfcheck_attempts')
    op.drop_table('sessions')
    op.drop_table('ingestion_jobs')
    op.drop_index('idx_chunks_embedding', table_name='chunks')
    op.drop_table('chunks')
    op.drop_table('documents')
    op.drop_table('users')
    op.execute('DROP EXTENSION IF EXISTS vector')
    op.execute("DROP TYPE IF EXISTS userrole")
