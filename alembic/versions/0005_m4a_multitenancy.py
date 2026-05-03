"""M4.A — multi-tenancy foundation

Adds:
  * `tenants` table (id, slug, display_name, status, config jsonb)
  * `tenant_id` column on users / documents / chunks / ingestion_jobs /
    sessions / selfcheck_attempts / qa_feedback
  * Per-user fields for M5/M7 governance: consent_recorded_at, deleted_at,
    jwt_version, supervisor_visibility (defaulted; M5 will make use)
  * Per-document lifecycle fields: status, superseded_by, quality_score
  * Wider role vocabulary (super-admin / tenant-admin / supervisor / student)
    via role TEXT + CHECK constraint (replaces M2 ENUM userrole)

Data migration:
  * Single tenant row with slug='default' is inserted.
  * Existing records bind to it.
  * Existing `admin` users → role='super-admin', tenant_id=NULL (cross-tenant).
  * Existing `user` users → role='student', tenant_id=default.

Note on `documents` vs `materials`: roadmap uses term "material"; codebase
uses table name `documents`. Keeping the table name to avoid churn — both
refer to the same concept.

Revision ID: 0005_m4a_multitenancy
Revises: 0004
Create Date: 2026-05-03
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0005_m4a_multitenancy"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── 1. tenants table ────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")  # for gen_random_uuid

    op.execute(
        """
        CREATE TABLE tenants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'read-only', 'archived')),
            config JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by UUID NULL
        )
        """
    )

    # Seed: the default tenant. M4.5 will rename it to 'optics-kafedra'.
    op.execute(
        """
        INSERT INTO tenants (slug, display_name)
        VALUES ('default', 'Default Tenant')
        """
    )

    # ─── 2. users — tenant_id, lifecycle/governance fields, role widening ─
    # Role widening: drop legacy enum, switch to TEXT + CHECK.
    # Order matters: DEFAULT references the enum type, so drop default first.
    op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE TEXT USING role::TEXT")
    op.execute("DROP TYPE IF EXISTS userrole")

    # Map legacy values to new vocabulary BEFORE adding CHECK constraint.
    op.execute("UPDATE users SET role = 'student' WHERE role = 'user'")
    op.execute("UPDATE users SET role = 'super-admin' WHERE role = 'admin'")

    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'student'")
    op.execute(
        """
        ALTER TABLE users ADD CONSTRAINT users_role_check
        CHECK (role IN ('super-admin', 'tenant-admin', 'supervisor', 'student'))
        """
    )

    op.add_column(
        "users",
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "users_tenant_id_fkey",
        "users",
        "tenants",
        ["tenant_id"],
        ["id"],
    )
    # Bind non-super-admin users to default tenant.
    op.execute(
        """
        UPDATE users
           SET tenant_id = (SELECT id FROM tenants WHERE slug = 'default')
         WHERE role <> 'super-admin'
        """
    )

    op.add_column("users", sa.Column("consent_recorded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("jwt_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "users",
        sa.Column(
            "supervisor_visibility",
            sa.Text(),
            nullable=False,
            server_default="anonymous-aggregate-only",
        ),
    )
    op.execute(
        """
        ALTER TABLE users ADD CONSTRAINT users_supervisor_visibility_check
        CHECK (supervisor_visibility IN ('anonymous-aggregate-only', 'show-to-supervisor'))
        """
    )
    op.add_column(
        "users", sa.Column("visibility_changed_at", sa.DateTime(timezone=True), nullable=True)
    )

    # ─── 3. documents — tenant_id + lifecycle ─────────────────────────────
    op.add_column(
        "documents",
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "documents_tenant_id_fkey",
        "documents",
        "tenants",
        ["tenant_id"],
        ["id"],
    )
    op.execute(
        "UPDATE documents "
        "SET tenant_id = (SELECT id FROM tenants WHERE slug = 'default')"
    )
    op.alter_column("documents", "tenant_id", nullable=False)

    op.add_column(
        "documents",
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="active",
        ),
    )
    op.execute(
        """
        ALTER TABLE documents ADD CONSTRAINT documents_status_check
        CHECK (status IN ('active', 'superseded', 'deleted'))
        """
    )
    op.add_column(
        "documents",
        sa.Column(
            "superseded_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("documents", sa.Column("quality_score", sa.Float(), nullable=True))

    # ─── 4. chunks — denormalized tenant_id + index for retrieval filter ──
    op.add_column(
        "chunks",
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE chunks c
           SET tenant_id = d.tenant_id
          FROM documents d
         WHERE c.document_id = d.id
        """
    )
    op.alter_column("chunks", "tenant_id", nullable=False)
    op.create_foreign_key(
        "chunks_tenant_id_fkey", "chunks", "tenants", ["tenant_id"], ["id"]
    )
    op.create_index("ix_chunks_tenant_id", "chunks", ["tenant_id"])

    # ─── 5. ingestion_jobs / sessions / selfcheck_attempts / qa_feedback ──
    for table_name, default_to_default_tenant in [
        ("ingestion_jobs", True),
        ("sessions", True),
        ("selfcheck_attempts", True),
        ("qa_feedback", True),
    ]:
        op.add_column(
            table_name,
            sa.Column(
                "tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True
            ),
        )
        if default_to_default_tenant:
            op.execute(
                f"UPDATE {table_name} "
                f"SET tenant_id = (SELECT id FROM tenants WHERE slug = 'default')"
            )
        op.alter_column(table_name, "tenant_id", nullable=False)
        op.create_foreign_key(
            f"{table_name}_tenant_id_fkey",
            table_name,
            "tenants",
            ["tenant_id"],
            ["id"],
        )
        op.create_index(f"ix_{table_name}_tenant_id", table_name, ["tenant_id"])

    # ─── 6. selfcheck_attempts — explicit status enum + nullable user_id ──
    # M5 BDD requires the status field as an enum (in_progress/completed/
    # abandoned/invalid_evaluation). M2 had it as free-form TEXT defaulting
    # to "created" — backfill old values to "completed", add CHECK.
    op.execute(
        """
        UPDATE selfcheck_attempts
           SET status = 'completed'
         WHERE status NOT IN ('in_progress', 'completed', 'abandoned', 'invalid_evaluation')
        """
    )
    op.execute(
        """
        ALTER TABLE selfcheck_attempts ADD CONSTRAINT selfcheck_attempts_status_check
        CHECK (status IN ('in_progress', 'completed', 'abandoned', 'invalid_evaluation'))
        """
    )
    # Allow user_id to become NULL after soft-delete + anonymization (BDD 7.3).
    op.alter_column("selfcheck_attempts", "user_id", nullable=True)

    # ─── 7. invite_codes table ────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE invite_codes (
            code TEXT PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id),
            role TEXT NOT NULL CHECK (role IN ('tenant-admin', 'supervisor', 'student')),
            created_by UUID REFERENCES users(id),
            expires_at TIMESTAMPTZ,
            redeemed_at TIMESTAMPTZ,
            redeemed_by UUID REFERENCES users(id)
        )
        """
    )
    op.create_index("ix_invite_codes_tenant_id", "invite_codes", ["tenant_id"])

    # ─── 8. audit_log table ───────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE audit_log (
            id BIGSERIAL PRIMARY KEY,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            actor_id UUID NULL,
            actor_role TEXT NULL,
            tenant_id UUID NULL REFERENCES tenants(id),
            action TEXT NOT NULL,
            target_type TEXT NULL,
            target_id TEXT NULL,
            request_id TEXT NULL,
            details JSONB NULL
        )
        """
    )
    op.create_index("ix_audit_log_tenant_id", "audit_log", ["tenant_id"])
    op.create_index("ix_audit_log_occurred_at", "audit_log", ["occurred_at"])

    # ─── 9. qa_feedback widening for BDD 1.8 ──────────────────────────────
    # Existing M2 qa_feedback has rating IN ('positive', 'negative'). BDD 1.8
    # adds a richer signal: the user can mark a specific answer as
    # "incorrect" with an optional comment, surfaced to tenant-admin as
    # eval-set candidate. We extend in place (single source of truth).
    op.add_column("qa_feedback", sa.Column("comment", sa.Text(), nullable=True))
    op.add_column(
        "qa_feedback", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "qa_feedback",
        sa.Column(
            "reviewed_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # M2 had user_id NOT NULL; allow NULL after user soft-delete.
    op.alter_column("qa_feedback", "user_id", nullable=True)


def downgrade() -> None:
    # qa_feedback rollback
    op.alter_column("qa_feedback", "user_id", nullable=False)
    op.drop_column("qa_feedback", "reviewed_by")
    op.drop_column("qa_feedback", "reviewed_at")
    op.drop_column("qa_feedback", "comment")

    op.drop_index("ix_audit_log_occurred_at", "audit_log")
    op.drop_index("ix_audit_log_tenant_id", "audit_log")
    op.execute("DROP TABLE audit_log")

    op.drop_index("ix_invite_codes_tenant_id", "invite_codes")
    op.execute("DROP TABLE invite_codes")

    # selfcheck_attempts rollback
    op.alter_column("selfcheck_attempts", "user_id", nullable=False)
    op.execute("ALTER TABLE selfcheck_attempts DROP CONSTRAINT IF EXISTS selfcheck_attempts_status_check")

    # tenant_id rollback for derivative tables
    for table_name in ["qa_feedback", "selfcheck_attempts", "sessions", "ingestion_jobs"]:
        op.drop_index(f"ix_{table_name}_tenant_id", table_name)
        op.drop_constraint(f"{table_name}_tenant_id_fkey", table_name, type_="foreignkey")
        op.drop_column(table_name, "tenant_id")

    # chunks rollback
    op.drop_index("ix_chunks_tenant_id", "chunks")
    op.drop_constraint("chunks_tenant_id_fkey", "chunks", type_="foreignkey")
    op.drop_column("chunks", "tenant_id")

    # documents rollback
    op.drop_column("documents", "quality_score")
    op.drop_column("documents", "superseded_by")
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_status_check")
    op.drop_column("documents", "status")
    op.drop_constraint("documents_tenant_id_fkey", "documents", type_="foreignkey")
    op.drop_column("documents", "tenant_id")

    # users rollback
    op.drop_column("users", "visibility_changed_at")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_supervisor_visibility_check")
    op.drop_column("users", "supervisor_visibility")
    op.drop_column("users", "jwt_version")
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "consent_recorded_at")
    op.drop_constraint("users_tenant_id_fkey", "users", type_="foreignkey")
    op.drop_column("users", "tenant_id")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check")
    # Map back: super-admin → admin, student → user (reverse data migration)
    op.execute("UPDATE users SET role = 'admin' WHERE role = 'super-admin'")
    op.execute("UPDATE users SET role = 'user' WHERE role IN ('student', 'tenant-admin', 'supervisor')")
    # Recreate legacy enum
    op.execute("CREATE TYPE userrole AS ENUM ('user', 'admin')")
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE userrole USING role::userrole")

    # tenants
    op.execute("DROP TABLE tenants")
