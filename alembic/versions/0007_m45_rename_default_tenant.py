"""M4.5.0 — rename default tenant → optics-kafedra (kafedral handoff)

This is the explicit handoff from M4.A's seed `default` tenant to the
M4.5 pilot tenant `optics-kafedra` (per roadmap §M4.5.A migration step).
It's a 2-line UPDATE; no row-level data movement.

Coupled change in code: `atlas.core.config.settings.pilot_tenant_slug`
is now `'optics-kafedra'`. The helper `get_default_tenant_id` reads
that setting, so super-admin without an explicit X-Atlas-Tenant header
operates against optics-kafedra by default.

Forward compatibility for environments still on the `default` slug
(e.g. fresh dev DBs from before this migration): tenant_helpers also
falls back to legacy `'default'` if the configured slug isn't found.

Revision ID: 0007_m45_rename_default_tenant
Revises: 0006_m4b_tenant_indexes
Create Date: 2026-05-04
"""
from __future__ import annotations

from alembic import op


revision = "0007_m45_rename_default_tenant"
down_revision = "0006_m4b_tenant_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename only if a tenant with slug='default' exists AND no tenant
    # with slug='optics-kafedra' exists yet (idempotent).
    op.execute(
        """
        UPDATE tenants
           SET slug = 'optics-kafedra',
               display_name = 'Кафедра оптики'
         WHERE slug = 'default'
           AND NOT EXISTS (SELECT 1 FROM tenants WHERE slug = 'optics-kafedra')
        """
    )

    # Recreate the partial HNSW index that was bound to the (now-defunct)
    # default tenant. The old index name `chunks_hnsw_default` references
    # the tenant by UUID in its WHERE clause, so it remains semantically
    # correct (UUID didn't change) but the name is now misleading.
    # We keep it in place; M4.5.B will add per-tenant index creation in
    # the Tenant.create() hook for new tenants.
    # No-op here — just documenting why the legacy name persists.


def downgrade() -> None:
    op.execute(
        """
        UPDATE tenants
           SET slug = 'default',
               display_name = 'Default Tenant'
         WHERE slug = 'optics-kafedra'
           AND NOT EXISTS (SELECT 1 FROM tenants WHERE slug = 'default')
        """
    )
