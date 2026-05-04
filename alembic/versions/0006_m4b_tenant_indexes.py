"""M4.B — tenant-scoped retrieval indexes

Adds:
  * Partial HNSW index on chunks.embedding for the 'default' tenant only
    (vector cosine ops). Pattern: when retrieval is bound to one tenant,
    the planner uses this partial index instead of the global HNSW
    (idx_chunks_embedding from M2). On a single-tenant pilot the difference
    is small; the value is establishing the pattern for M4.5+ when each
    new tenant gets its own partial index in the `tenant.create()` hook.
  * Partial index on documents(tenant_id) WHERE status='active' — speeds
    up the retrieval JOIN filter that excludes superseded/deleted docs
    (M4.A introduced lifecycle status).

Revision ID: 0006_m4b_tenant_indexes
Revises: 0005_m4a_multitenancy
Create Date: 2026-05-03
"""
from __future__ import annotations

from alembic import op


revision = "0006_m4b_tenant_indexes"
down_revision = "0005_m4a_multitenancy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Partial HNSW per default tenant. Uses DO + EXECUTE format() because the
    # tenant UUID isn't known at migration-write time.
    op.execute(
        """
        DO $$
        DECLARE
            default_id UUID;
        BEGIN
            SELECT id INTO default_id FROM tenants WHERE slug = 'default';
            IF default_id IS NULL THEN
                RAISE EXCEPTION 'default tenant not found — was migration 0005 applied?';
            END IF;
            EXECUTE format(
                'CREATE INDEX IF NOT EXISTS chunks_hnsw_default '
                'ON chunks USING hnsw (embedding vector_cosine_ops) '
                'WITH (m=16, ef_construction=64) '
                'WHERE tenant_id = %L',
                default_id
            );
        END $$;
        """
    )

    # Partial B-tree on documents.tenant_id WHERE status='active'.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS documents_tenant_active_idx
        ON documents (tenant_id)
        WHERE status = 'active'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS documents_tenant_active_idx")
    op.execute("DROP INDEX IF EXISTS chunks_hnsw_default")
