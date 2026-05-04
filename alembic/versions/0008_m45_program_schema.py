"""M4.5.B — programs / topics / material-topic mappings

Per roadmap §M4.5.B. Adds the topic-aware retrieval substrate:

  * `programs` — one active row per tenant, archived versions stay for
    historical attempts (BDD 7.4).
  * `program_topics` — billet (тема программы) entries; foreign key to
    program. external_id is the human-readable slug from program.md
    (e.g. "1.3"); coverage_chunks is a denormalized counter updated by
    triggers in M4.5.D.
  * `material_topics` — many-to-many between documents and program
    topics (a doc can cover several billets).
  * `chunk_topics` — denormalized inheritance from material_topics so
    retrieval can JOIN once on chunks. Trigger handles INSERT / UPDATE /
    DELETE on material_topics → keeps chunk_topics consistent.

ON DELETE policy (per roadmap M4.5.B):
  * `chunks` cascade-deletes chunk_topics (chunk gone → references gone).
  * `program_topics` are append-only (RESTRICT) — even archived programs
    keep their topics so attempts referencing them stay resolvable.
  * `self_check_attempts.topic_id` (added here) → RESTRICT for the
    same reason.

Revision ID: 0008_m45_program_schema
Revises: 0007_m45_rename_default_tenant
Create Date: 2026-05-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_m45_program_schema"
down_revision = "0007_m45_rename_default_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── programs ─────────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE programs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id),
            version TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'archived')),
            source_doc TEXT,
            loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            loaded_by UUID REFERENCES users(id)
        )
        """
    )
    # At most one active program per tenant — partial unique index.
    op.execute(
        """
        CREATE UNIQUE INDEX programs_one_active
        ON programs (tenant_id) WHERE status = 'active'
        """
    )
    op.create_index("ix_programs_tenant_id", "programs", ["tenant_id"])

    # ─── program_topics ───────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE program_topics (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            program_id UUID NOT NULL REFERENCES programs(id),
            external_id TEXT NOT NULL,
            section TEXT NOT NULL,
            title TEXT NOT NULL,
            ordinal INT NOT NULL,
            key_concepts TEXT[] NOT NULL DEFAULT '{}',
            coverage_chunks INT NOT NULL DEFAULT 0,
            UNIQUE (program_id, external_id)
        )
        """
    )
    op.create_index("ix_program_topics_program_id", "program_topics", ["program_id"])

    # ─── material_topics ──────────────────────────────────────────────────
    # M2N between documents and program_topics.
    op.execute(
        """
        CREATE TABLE material_topics (
            material_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            topic_id UUID NOT NULL REFERENCES program_topics(id) ON DELETE RESTRICT,
            PRIMARY KEY (material_id, topic_id)
        )
        """
    )
    op.create_index(
        "ix_material_topics_topic_id", "material_topics", ["topic_id"]
    )

    # ─── chunk_topics ─────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE chunk_topics (
            chunk_id UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
            topic_id UUID NOT NULL REFERENCES program_topics(id) ON DELETE RESTRICT,
            PRIMARY KEY (chunk_id, topic_id)
        )
        """
    )
    op.create_index("ix_chunk_topics_topic_id", "chunk_topics", ["topic_id"])

    # ─── Trigger: material_topics → chunk_topics propagation ──────────────
    # When tenant-admin attaches/detaches topics on a material, every chunk
    # inherits the change. The trigger fires for INSERT, UPDATE, DELETE on
    # material_topics; affects all chunks of that material.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sync_chunk_topics_on_material_topic()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                INSERT INTO chunk_topics (chunk_id, topic_id)
                SELECT c.id, NEW.topic_id
                FROM chunks c
                WHERE c.document_id = NEW.material_id
                ON CONFLICT DO NOTHING;
                RETURN NEW;
            ELSIF TG_OP = 'DELETE' THEN
                DELETE FROM chunk_topics ct
                USING chunks c
                WHERE ct.chunk_id = c.id
                  AND c.document_id = OLD.material_id
                  AND ct.topic_id = OLD.topic_id;
                RETURN OLD;
            ELSIF TG_OP = 'UPDATE' THEN
                -- topic_id changed: drop old, add new
                DELETE FROM chunk_topics ct
                USING chunks c
                WHERE ct.chunk_id = c.id
                  AND c.document_id = OLD.material_id
                  AND ct.topic_id = OLD.topic_id;
                INSERT INTO chunk_topics (chunk_id, topic_id)
                SELECT c.id, NEW.topic_id
                FROM chunks c
                WHERE c.document_id = NEW.material_id
                ON CONFLICT DO NOTHING;
                RETURN NEW;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER material_topics_sync_chunk_topics
        AFTER INSERT OR UPDATE OR DELETE ON material_topics
        FOR EACH ROW EXECUTE FUNCTION sync_chunk_topics_on_material_topic();
        """
    )

    # ─── Trigger: chunks INSERT propagates parent's material_topics ───────
    # When a brand-new chunk is created (ingestion), seed its chunk_topics
    # from the parent material's existing material_topics.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION seed_chunk_topics_on_chunk_insert()
        RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO chunk_topics (chunk_id, topic_id)
            SELECT NEW.id, mt.topic_id
            FROM material_topics mt
            WHERE mt.material_id = NEW.document_id
            ON CONFLICT DO NOTHING;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER chunks_seed_chunk_topics
        AFTER INSERT ON chunks
        FOR EACH ROW EXECUTE FUNCTION seed_chunk_topics_on_chunk_insert();
        """
    )

    # ─── Trigger: chunk_topics → program_topics.coverage_chunks counter ───
    # Denormalized counter updated on every chunk_topics change AND on
    # documents.status change (via separate trigger below). counts only
    # chunks belonging to documents with status='active'.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_topic_coverage_on_chunk_topic()
        RETURNS TRIGGER AS $$
        DECLARE
            doc_status TEXT;
            target_topic UUID;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                target_topic := NEW.topic_id;
                SELECT d.status INTO doc_status
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE c.id = NEW.chunk_id;
                IF doc_status = 'active' THEN
                    UPDATE program_topics
                    SET coverage_chunks = coverage_chunks + 1
                    WHERE id = target_topic;
                END IF;
                RETURN NEW;
            ELSIF TG_OP = 'DELETE' THEN
                target_topic := OLD.topic_id;
                SELECT d.status INTO doc_status
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE c.id = OLD.chunk_id;
                IF doc_status = 'active' THEN
                    UPDATE program_topics
                    SET coverage_chunks = GREATEST(coverage_chunks - 1, 0)
                    WHERE id = target_topic;
                END IF;
                RETURN OLD;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER chunk_topics_update_coverage
        AFTER INSERT OR DELETE ON chunk_topics
        FOR EACH ROW EXECUTE FUNCTION update_topic_coverage_on_chunk_topic();
        """
    )

    # ─── Trigger: documents.status change → coverage delta ────────────────
    # When a doc transitions active ↔ {superseded, deleted}, every chunk's
    # contribution to its topics flips. Recompute affected counters.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_topic_coverage_on_document_status()
        RETURNS TRIGGER AS $$
        DECLARE
            delta INT;
        BEGIN
            IF OLD.status = NEW.status THEN
                RETURN NEW;
            END IF;
            IF NEW.status = 'active' AND OLD.status <> 'active' THEN
                delta := 1;
            ELSIF OLD.status = 'active' AND NEW.status <> 'active' THEN
                delta := -1;
            ELSE
                RETURN NEW;  -- not active either way: no change.
            END IF;
            UPDATE program_topics pt
            SET coverage_chunks = GREATEST(coverage_chunks + delta * sub.cnt, 0)
            FROM (
                SELECT ct.topic_id, COUNT(*) AS cnt
                FROM chunk_topics ct
                JOIN chunks c ON c.id = ct.chunk_id
                WHERE c.document_id = NEW.id
                GROUP BY ct.topic_id
            ) sub
            WHERE pt.id = sub.topic_id;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER documents_status_update_coverage
        AFTER UPDATE OF status ON documents
        FOR EACH ROW EXECUTE FUNCTION update_topic_coverage_on_document_status();
        """
    )

    # ─── self_check_attempts.topic_id (M5 dependency) ─────────────────────
    # Optional FK — null for legacy/free-text attempts.
    op.add_column(
        "selfcheck_attempts",
        sa.Column(
            "topic_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("program_topics.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_selfcheck_attempts_topic_id", "selfcheck_attempts", ["topic_id"]
    )

    # ─── qa_sessions.topic_id (M5 / drilldown analytics) ──────────────────
    op.add_column(
        "sessions",
        sa.Column(
            "topic_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("program_topics.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "topic_id")
    op.drop_index("ix_selfcheck_attempts_topic_id", "selfcheck_attempts")
    op.drop_column("selfcheck_attempts", "topic_id")

    op.execute("DROP TRIGGER IF EXISTS documents_status_update_coverage ON documents")
    op.execute("DROP FUNCTION IF EXISTS update_topic_coverage_on_document_status()")

    op.execute("DROP TRIGGER IF EXISTS chunk_topics_update_coverage ON chunk_topics")
    op.execute("DROP FUNCTION IF EXISTS update_topic_coverage_on_chunk_topic()")

    op.execute("DROP TRIGGER IF EXISTS chunks_seed_chunk_topics ON chunks")
    op.execute("DROP FUNCTION IF EXISTS seed_chunk_topics_on_chunk_insert()")

    op.execute("DROP TRIGGER IF EXISTS material_topics_sync_chunk_topics ON material_topics")
    op.execute("DROP FUNCTION IF EXISTS sync_chunk_topics_on_material_topic()")

    op.execute("DROP TABLE chunk_topics")
    op.execute("DROP TABLE material_topics")
    op.drop_index("ix_program_topics_program_id", "program_topics")
    op.execute("DROP TABLE program_topics")
    op.drop_index("ix_programs_tenant_id", "programs")
    op.execute("DROP INDEX IF EXISTS programs_one_active")
    op.execute("DROP TABLE programs")
