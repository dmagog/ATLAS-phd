import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Float, Integer, DateTime, ForeignKey,
    JSON, Boolean, UniqueConstraint, BigInteger, CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector
from atlas.db.base import Base
import enum


class UserRole(str, enum.Enum):
    """Application-level vocabulary for users.role.

    Persisted as TEXT with a CHECK constraint (see migration 0005). M2 had a
    Postgres ENUM `userrole` with two values; M4.A widens to four.
    """

    super_admin = "super-admin"
    tenant_admin = "tenant-admin"
    supervisor = "supervisor"
    student = "student"


class TenantStatus(str, enum.Enum):
    active = "active"
    read_only = "read-only"
    archived = "archived"


class DocumentStatus(str, enum.Enum):
    active = "active"
    superseded = "superseded"
    deleted = "deleted"


class SupervisorVisibility(str, enum.Enum):
    anonymous = "anonymous-aggregate-only"
    show = "show-to-supervisor"


class SelfCheckStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"
    abandoned = "abandoned"
    invalid_evaluation = "invalid_evaluation"


# ─── M4.A: Tenants ────────────────────────────────────────────────────────
class Tenant(Base):
    """A direction (направление) of kandidate-exam preparation. M4.A foundation
    of multi-tenant mode; per roadmap §1.4 each tenant = one specialty.
    """

    __tablename__ = "tenants"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(Text, unique=True, nullable=False)
    display_name = Column(Text, nullable=False)
    status = Column(Text, default=TenantStatus.active.value, nullable=False)
    config = Column(JSONB, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    created_by = Column(UUID(as_uuid=True), nullable=True)


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    # role: TEXT + CHECK constraint at DB level (see migration 0005). Application
    # uses UserRole enum for validation; we don't bind SAEnum to avoid Postgres
    # ENUM mutation pain.
    role = Column(Text, default=UserRole.student.value, nullable=False)
    # tenant_id is NULL for super-admin (cross-tenant); other roles must be bound.
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    consent_recorded_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    # Bumped on role-revocation / forced logout — issued JWTs with older
    # `jv` claim become invalid (BDD 7.5).
    jwt_version = Column(Integer, default=1, nullable=False)
    # M5 privacy toggle (BDD 3.4). Default keeps personal data anonymized
    # in supervisor analytics.
    supervisor_visibility = Column(
        Text, default=SupervisorVisibility.anonymous.value, nullable=False
    )
    visibility_changed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Document(Base):
    __tablename__ = "documents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    title = Column(String(512), nullable=False)
    filename = Column(String(512), nullable=False)
    sha256 = Column(String(64), unique=True, nullable=False)
    file_path = Column(String(1024), nullable=False)
    mime_type = Column(String(128), nullable=False)
    # Lifecycle (BDD 4.13, 4.7). retrieval filters status='active'.
    status = Column(Text, default=DocumentStatus.active.value, nullable=False)
    superseded_by = Column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    quality_score = Column(Float, nullable=True)  # BDD 4.8; calibrated in M4.5.D
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Chunk(Base):
    __tablename__ = "chunks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    # Denormalized from documents.tenant_id — keeps retrieval queries from
    # JOINing on every fetch (M4 partial HNSW per-tenant strategy).
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    section = Column(String(512), nullable=True)
    page = Column(Integer, nullable=True)
    embedding = Column(Vector(384), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("document_id", "chunk_index"),)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    status = Column(String(32), default="created", nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    accepted_files = Column(JSON, default=list)
    rejected_files = Column(JSON, default=list)
    progress_info = Column(JSON, nullable=True)


class Session(Base):
    __tablename__ = "sessions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    mode = Column(String(32), default="qa", nullable=False)
    response_profile = Column(String(32), default="detailed", nullable=False)
    history = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class QAFeedback(Base):
    """User feedback on a Q&A response (BDD 1.8 + M2 thumb-up/down).

    Two signal vocabularies coexist on `rating`:
      * M2 UI: "positive" / "negative" (thumb buttons)
      * BDD 1.8: "incorrect" (with optional comment, surfaced to
        tenant-admin as eval-set candidate)
    Treated uniformly; tenant-admin sees them in one panel.
    """

    __tablename__ = "qa_feedback"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )  # nullable after soft-delete anonymization
    request_id = Column(String(64), nullable=False, index=True)
    rating = Column(String(16), nullable=False)
    question_text = Column(Text, nullable=True)
    answer_markdown = Column(Text, nullable=True)
    comment = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SelfCheckAttempt(Base):
    __tablename__ = "selfcheck_attempts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )  # nullable after soft-delete anonymization (BDD 7.3)
    topic = Column(String(512), nullable=False)
    # M5: FK to program_topics so supervisor heatmap can aggregate per-topic.
    # Nullable for legacy attempts created before the FK was wired up.
    topic_id = Column(
        UUID(as_uuid=True),
        ForeignKey("program_topics.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    language = Column(String(8), default="ru", nullable=False)
    status = Column(String(32), default=SelfCheckStatus.completed.value, nullable=False)
    question_set = Column(JSON, nullable=True)
    answers = Column(JSON, nullable=True)
    evaluation = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


# ─── M4.A: invite_codes + audit_log ───────────────────────────────────────
class InviteCode(Base):
    """One-time invite tokens for joining a tenant in a specific role.

    Roadmap M4.C; redeemed_at + redeemed_by track usage. Expires_at lets
    tenant-admin set a TTL; default applied at issuance.
    """

    __tablename__ = "invite_codes"
    code = Column(Text, primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    role = Column(Text, nullable=False)  # CHECK constraint in DB
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    redeemed_at = Column(DateTime(timezone=True), nullable=True)
    redeemed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


# ─── M4.5: Programs / topics / mappings ───────────────────────────────────


class ProgramStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class Program(Base):
    """Kandekzamen-программа for one tenant. Append+archive — never delete.
    BDD 7.4: only one row with status='active' per tenant (partial unique
    index `programs_one_active` enforces it).
    """

    __tablename__ = "programs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    version = Column(Text, nullable=False)
    status = Column(Text, default=ProgramStatus.active.value, nullable=False)
    source_doc = Column(Text, nullable=True)
    loaded_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    loaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class ProgramTopic(Base):
    """A billet (тема программы). external_id is the human-readable slug
    from program.md (e.g. "1.3"); coverage_chunks is denormalized counter
    maintained by triggers.
    """

    __tablename__ = "program_topics"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=False)
    external_id = Column(Text, nullable=False)
    section = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    ordinal = Column(Integer, nullable=False)
    # ARRAY type via Postgres-specific.
    from sqlalchemy.dialects.postgresql import ARRAY  # noqa: WPS433
    key_concepts = Column(ARRAY(Text), default=list, nullable=False)
    coverage_chunks = Column(Integer, default=0, nullable=False)
    __table_args__ = (UniqueConstraint("program_id", "external_id"),)


class MaterialTopic(Base):
    """Many-to-many between documents (materials) and program topics.
    Composite PK enforces (material_id, topic_id) uniqueness."""

    __tablename__ = "material_topics"
    material_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    topic_id = Column(
        UUID(as_uuid=True),
        ForeignKey("program_topics.id", ondelete="RESTRICT"),
        primary_key=True,
    )


class ChunkTopic(Base):
    """Denormalized inheritance: every chunk inherits all topics of its
    parent material. Maintained by Postgres triggers (see migration 0008);
    application code rarely writes here directly."""

    __tablename__ = "chunk_topics"
    chunk_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chunks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    topic_id = Column(
        UUID(as_uuid=True),
        ForeignKey("program_topics.id", ondelete="RESTRICT"),
        primary_key=True,
    )


class AuditLog(Base):
    """Append-only audit trail. tenant_id NULL for platform-level events
    (e.g. tenant.create by super-admin). BDD 7.1 / 7.6.
    """

    __tablename__ = "audit_log"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    actor_id = Column(UUID(as_uuid=True), nullable=True)
    actor_role = Column(Text, nullable=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    action = Column(Text, nullable=False)
    target_type = Column(Text, nullable=True)
    target_id = Column(Text, nullable=True)
    request_id = Column(Text, nullable=True)
    details = Column(JSONB, nullable=True)
